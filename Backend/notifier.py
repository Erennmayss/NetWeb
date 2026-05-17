"""
IDS Alert Notifier - Surveillance en arrière-plan (Windows)
============================================================
Lance ce script une fois → il tourne en tâche de fond et envoie
des notifications Windows toast à chaque nouvelle alerte détectée,
même si le dashboard est fermé.
 
Dépendances :
    pip install plyer requests psycopg2-binary win10toast-persist winotify winrt
 
Usage :
    python notifier.py
    python notifier.py --api http://localhost:5000    (URL Flask personnalisée)
    python notifier.py --interval 5                   (polling toutes les 5s)
    python notifier.py --db                           (connexion directe DB, sans Flask)
"""

import argparse
import sys
import time
import logging
import threading
import os
import json
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
CONFIG_DIR = Path(os.getenv("APPDATA")) / "IDS_Notifier"
CONFIG_DIR.mkdir(exist_ok=True)
STATE_FILE = CONFIG_DIR / "notifier_state.json"
LOG_FILE = CONFIG_DIR / "notifier.log"


def _load_runtime_env():
    """Charge les variables depuis %APPDATA%\\IDS_Notifier\\(.env|notifier.conf|email_config.json)."""
    for config_path in (CONFIG_DIR / ".env", CONFIG_DIR / "notifier.conf"):
        if not config_path.exists():
            continue

        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue

                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key:
                        os.environ.setdefault(key, value)
        except Exception as exc:
            print(f"[WARN] Impossible de charger {config_path}: {exc}")

    email_config_path = CONFIG_DIR / "email_config.json"
    if email_config_path.exists():
        try:
            with open(email_config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            mapping = {
                "smtp_server": "SMTP_HOST",
                "smtp_port": "SMTP_PORT",
                "smtp_user": "SMTP_USER",
                "smtp_password": "SMTP_PASSWORD",
                "use_tls": "SMTP_USE_TLS",
                "from_email": "SMTP_FROM",
            }

            # email_config.json est la source de vérité pour le SMTP :
            # on force SMTP_ENABLED=true et on écrase les variables SMTP
            # même si .env ou notifier.conf les avaient définies autrement.
            os.environ["SMTP_ENABLED"] = "true"
            for src_key, env_key in mapping.items():
                if src_key in data and data[src_key] is not None:
                    os.environ[env_key] = str(data[src_key])
        except Exception as exc:
            print(f"[WARN] Impossible de charger {email_config_path}: {exc}")


_load_runtime_env()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ids-notifier")


# ── Gestion d'état persistant ───────────────────────────────────────────────
def load_state():
    """Charge le dernier ID vu depuis le fichier d'état"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                return set(state.get('seen_ids', [])), state.get('last_check', 0)
        except:
            pass
    return set(), 0

def save_state(seen_ids):
    """Sauvegarde les IDs vus"""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({
                'seen_ids': list(seen_ids),
                'last_check': time.time()
            }, f)
    except Exception as e:
        log.error(f"Erreur sauvegarde état: {e}")

def get_machine_guid():
    """Identifiant unique pour éviter les doublons sur multi-sessions"""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                            r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        return guid
    except:
        return "default"


def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "oui"}


def get_db_config():
    """
    Lit la configuration DB depuis les variables d'environnement chargées
    par _load_runtime_env() (fichiers .env / notifier.conf dans CONFIG_DIR).
    Aucune valeur par défaut hardcodée : toute la config vient du fichier de config.
    """
    required = {
        "DB_NAME": os.getenv("DB_NAME"),
        "DB_USER": os.getenv("DB_USER"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD"),
        "DB_HOST": os.getenv("DB_HOST"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        log.error(
            f"Configuration DB incomplète — variables manquantes : {', '.join(missing)}. "
            f"Vérifiez {CONFIG_DIR / '.env'} ou {CONFIG_DIR / 'notifier.conf'}."
        )
        raise RuntimeError(f"DB config incomplète : {missing}")

    return {
        "dbname":   required["DB_NAME"],
        "user":     required["DB_USER"],
        "password": required["DB_PASSWORD"],
        "host":     required["DB_HOST"],
        "port":     required["DB_PORT"],
    }


def normalize_severity(value):
    sev_raw = (value or "").lower()
    if sev_raw in ("critical", "critique", "high", "élevée", "elevee"):
        return "critical"
    if sev_raw in ("medium", "moyen", "moyenne"):
        return "medium"
    return "low"


# ════════════════════════════════════════════════════════════════════════════
#  NOTIFICATIONS EMAIL POUR LES ADMINS (VERSION CORRIGÉE)
# ════════════════════════════════════════════════════════════════════════════
class AdminEmailNotifier:
    def __init__(self, db_cfg):
        self.db_cfg = db_cfg
        self.enabled = parse_bool(os.getenv("SMTP_ENABLED"), default=False)
        self.smtp_host = os.getenv("SMTP_HOST", "").strip()
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "").strip()
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM", "").strip()
        self.use_tls = parse_bool(os.getenv("SMTP_USE_TLS"), default=True)
        self.use_ssl = parse_bool(os.getenv("SMTP_USE_SSL"), default=False)
        self.subject_prefix = os.getenv("SMTP_SUBJECT_PREFIX", "[IDS]")
        if "gmail.com" in self.smtp_host.lower():
            self.smtp_password = self.smtp_password.replace(" ", "")
        self._sent_alert_ids = set()
        self._lock = threading.Lock()

    def is_ready(self):
        """Vérifie si la configuration SMTP est complète"""
        return self.enabled and bool(self.smtp_host and self.smtp_from)

    def _fetch_admin_emails(self):
        """Récupère les emails des utilisateurs avec le rôle ADMIN ou SECURITY_ADMIN"""
        try:
            import psycopg2
        except ImportError:
            log.error("psycopg2 introuvable: impossible de récupérer les emails admin")
            return []

        conn = None
        try:
            conn = psycopg2.connect(**self.db_cfg, connect_timeout=5)
            cur = conn.cursor()
            # Récupère les emails des rôles 'admin' ET 'security_admin'
            cur.execute("""
                SELECT DISTINCT TRIM(email)
                FROM utilisateur
                WHERE LOWER(TRIM(role)) IN ('admin', 'security_admin')
                  AND email IS NOT NULL
                  AND TRIM(email) <> ''
            """)
            emails = [row[0] for row in cur.fetchall() if row[0]]
            if emails:
                log.info(f"📧 {len(emails)} email(s) admin/security_admin trouvé(s) dans la base")
            else:
                log.warning("⚠️ Aucun email admin ou security_admin trouvé - Vérifiez la table utilisateur")
            return emails
        except Exception as exc:
            log.error(f"Impossible de récupérer les emails admin: {exc}")
            return []
        finally:
            if conn:
                conn.close()

    def _build_subject(self, alert):
        """Construit le sujet de l'email selon la sévérité"""
        severity_labels = {
            "critical": "CRITIQUE",
            "medium": "MOYENNE",
            "low": "FAIBLE",
        }
        sev = normalize_severity(alert.get("severity"))
        label = severity_labels.get(sev, sev.upper())
        name = alert.get("name", "Alerte inconnue")
        return f"{self.subject_prefix} Alerte {label} - {name}"

    def _build_body(self, alert):
        """Construit le corps de l'email"""
        ts = alert.get("timestamp") or datetime.now().isoformat()
        details = alert.get("details")
        if isinstance(details, dict):
            details_text = json.dumps(details, ensure_ascii=False, indent=2)
        elif details:
            details_text = str(details)
        else:
            details_text = "Aucun détail supplémentaire."

        return "\n".join([
            "=" * 60,
            "🚨 IDS - NOUVELLE ALERTE DÉTECTÉE 🚨",
            "=" * 60,
            "",
            f"🆔 ID: {alert.get('id', 'N/A')}",
            f"📋 Type: {alert.get('name', 'Alerte inconnue')}",
            f"⚠️ Sévérité: {normalize_severity(alert.get('severity')).upper()}",
            f"🖥️ Source: {alert.get('src', '?')}",
            f"🎯 Destination: {alert.get('dst', '?')}",
            f"🔌 Protocole: {alert.get('proto', 'N/A')}",
            f"🕐 Horodatage: {ts}",
            "",
            "📝 DÉTAILS:",
            "-" * 40,
            details_text,
            "",
            "=" * 60,
            "⚠️ Action recommandée: Vérifier immédiatement cette alerte",
            "=" * 60,
        ])

    def _send_message(self, recipient, subject, body):
        """Envoie un email à un destinataire"""
        message = EmailMessage()
        message["From"] = self.smtp_from
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body, charset="utf-8")

        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                    if self.smtp_user:
                        server.login(self.smtp_user, self.smtp_password)
                    server.send_message(message)
                return True

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.ehlo()
                if self.use_tls:
                    server.starttls()
                    server.ehlo()
                if self.smtp_user:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(message)
            return True
        except Exception as exc:
            log.error(f"Échec envoi à {recipient}: {exc}")
            return False

    def send_alert_email(self, alert):
        """Envoie l'alerte par email à tous les admins"""
        alert_id = alert.get("id")
        with self._lock:
            if alert_id in self._sent_alert_ids:
                log.debug(f"Alerte {alert_id} déjà envoyée par email")
                return
            self._sent_alert_ids.add(alert_id)
            # Nettoyer l'historique si trop grand
            if len(self._sent_alert_ids) > 1000:
                self._sent_alert_ids = set(list(self._sent_alert_ids)[-500:])

        if not self.is_ready():
            log.debug("Email admin désactivé ou configuration SMTP incomplète")
            return

        recipients = self._fetch_admin_emails()
        if not recipients:
            log.warning("⚠️ Aucun utilisateur ADMIN ou SECURITY_ADMIN avec email trouvé")
            log.warning("   Vérifiez que des utilisateurs ont role='admin' ou role='security_admin' et un email valide")
            return

        subject = self._build_subject(alert)
        body = self._build_body(alert)

        log.info(f"📧 Envoi de l'alerte à {len(recipients)} admin(s)...")
        
        success_count = 0
        for recipient in recipients:
            if self._send_message(recipient, subject, body):
                success_count += 1
                log.info(f"   ✓ Email envoyé à {recipient}")

        if success_count == len(recipients):
            log.info(f"✅ {success_count} email(s) envoyé(s) avec succès")
        else:
            log.warning(f"⚠️ {success_count}/{len(recipients)} emails envoyés")


# ── Notification Windows améliorée (multi-méthodes) ─────────────────────────
class WindowsNotifier:
    def __init__(self):
        self.notification_id = 1
        self.last_toast_time = {}
        
    def _get_toast_priority(self, severity):
        """Définit la priorité selon la sévérité"""
        priorities = {
            "critical": "required",
            "medium": "high", 
            "low": "normal"
        }
        return priorities.get(severity, "normal")
    
    def _notify_winrt(self, title, message, severity="normal"):
        """Utilise Windows.Runtime (plus moderne et fiable)"""
        try:
            from winrt.windows.ui.notifications import (
                ToastNotificationManager, ToastNotification, 
                ToastTemplateType, ToastDuration
            )
            from winrt.windows.data.xml.dom import XmlDocument
            
            template = ToastTemplateType.TOAST_TEXT02
            toast_xml = ToastNotificationManager.get_template_content(template)
            
            xml_doc = XmlDocument()
            xml_doc.load_xml(toast_xml)
            text_nodes = xml_doc.get_elements_by_tag_name("text")
            text_nodes[0].append_child(xml_doc.create_text_node(title))
            text_nodes[1].append_child(xml_doc.create_text_node(message))
            
            duration = ToastDuration.LONG if severity == "critical" else ToastDuration.SHORT
            toast = ToastNotification(xml_doc)
            toast.expiration_time = datetime.now() + timedelta(seconds=30)
            
            notifier = ToastNotificationManager.create_toast_notifier("IDS Monitor")
            notifier.show(toast)
            return True
        except Exception as e:
            log.debug(f"WinRT failed: {e}")
            return False
    
    def _notify_win10toast(self, title, message, severity="normal"):
        """Utilise win10toast-persist pour notifications persistantes"""
        try:
            from win10toast_persist import ToastNotifier
            
            duration = 10 if severity == "critical" else 6
            icon_path = Path(__file__).parent / "icon.ico"
            icon = str(icon_path) if icon_path.exists() else None
            
            toaster = ToastNotifier()
            toaster.show_toast(
                title, message,
                icon_path=icon,
                duration=duration,
                threaded=True
            )
            return True
        except Exception as e:
            log.debug(f"win10toast failed: {e}")
            return False
    
    def _notify_plyer(self, title, message, severity="normal"):
        """Fallback avec plyer"""
        try:
            from plyer import notification
            notification.notify(
                title=title[:64],
                message=message[:256],
                app_name="IDS Monitor",
                app_icon=None,
                timeout=8,
                ticker="IDS Alert"
            )
            return True
        except Exception as e:
            log.debug(f"Plyer failed: {e}")
            return False
    
    def _notify_winotify(self, title, message, severity="normal"):
        """Utilise winotify pour plus de contrôle"""
        try:
            from winotify import Notification, audio
            
            notif = Notification(
                app_id="IDS Monitor",
                title=title[:64],
                msg=message[:256],
                duration="long" if severity == "critical" else "short"
            )
            
            if severity == "critical":
                notif.set_audio(audio.Default, loop=False)
                
            notif.show()
            return True
        except Exception as e:
            log.debug(f"Winotify failed: {e}")
            return False
    
    def _notify_messagebox(self, title, message, severity="normal"):
        """Dernier recours : MessageBox"""
        try:
            import ctypes
            flags = 0x40 | 0x40000  # Info + Topmost
            if severity == "critical":
                flags = 0x30 | 0x40000  # Warning + Topmost
            ctypes.windll.user32.MessageBoxW(0, message[:256], title[:64], flags)
            return True
        except:
            return False
    
    def notify(self, title, message, severity="normal"):
        """Envoie une notification en essayant plusieurs méthodes"""
        current_time = time.time()
        if title in self.last_toast_time:
            if current_time - self.last_toast_time[title] < 2:
                return
        
        methods = [
            self._notify_winrt,
            self._notify_win10toast,
            self._notify_winotify,
            self._notify_plyer,
            self._notify_messagebox
        ]
        
        for method in methods:
            if method(title, message, severity):
                self.last_toast_time[title] = current_time
                return True
        
        log.error("Aucune méthode de notification n'a fonctionné")
        return False


# ── Sons d'alerte personnalisés ─────────────────────────────────────────────
def play_alert_sound(severity="normal"):
    """Joue un son selon la sévérité de l'alerte"""
    try:
        import winsound
        sounds = {
            "critical": (1000, 500),
            "medium": (800, 300),
            "low": (600, 200),
            "normal": (500, 150)
        }
        freq, duration = sounds.get(severity, (500, 150))
        winsound.Beep(freq, duration)
    except:
        pass


# ════════════════════════════════════════════════════════════════════════════
#  MODE 1 — Surveillance via l'API Flask
# ════════════════════════════════════════════════════════════════════════════
def watch_api(api_base: str, interval: int, notifier: WindowsNotifier, email_notifier=None):
    import requests
    
    log.info(f"Démarrage surveillance API → {api_base}  (toutes les {interval}s)")
    seen_ids, last_check = load_state()
    first_run = len(seen_ids) == 0
    
    # Tester la connexion API
    max_retries = 5
    for i in range(max_retries):
        try:
            resp = requests.get(f"{api_base}/api/health", timeout=5)
            if resp.status_code == 200:
                log.info(f"✅ API accessible : {api_base}")
                break
        except:
            if i < max_retries - 1:
                log.warning(f"⏳ Attente API... ({i+1}/{max_retries})")
                time.sleep(3)
            else:
                log.error(f"❌ API injoignable après {max_retries} tentatives: {api_base}")
                log.error("Vérifiez que le dashboard Flask est lancé (python app.py)")
                sys.exit(1)
    
    consecutive_errors = 0
    
    while True:
        try:
            resp = requests.get(
                f"{api_base}/api/alerts",
                params={"limit": 200, "sort": "newest"},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            consecutive_errors = 0
            
            if not data.get("success"):
                log.warning(f"API : succès=False → {data.get('error')}")
            else:
                alerts = data.get("alerts", [])
                new_alerts = [a for a in alerts if a["id"] not in seen_ids]
                
                if new_alerts:
                    log.info(f"📨 {len(new_alerts)} nouvelle(s) alerte(s) détectée(s)")
                    
                    for a in sorted(new_alerts, key=lambda x: x.get("timestamp", "")):
                        seen_ids.add(a["id"])
                        
                        sev = a.get("severity", "low")
                        if sev == "critical":
                            threading.Thread(target=play_alert_sound, args=("critical",), daemon=True).start()
                            threading.Thread(target=_handle_new_alert, args=(a, notifier, email_notifier), daemon=True).start()
                            time.sleep(2)
                            threading.Thread(target=_handle_new_alert, args=(a, notifier, email_notifier), daemon=True).start()
                        else:
                            threading.Thread(target=_handle_new_alert, args=(a, notifier, email_notifier), daemon=True).start()
                    
                    if len(seen_ids) % 10 == 0:
                        save_state(seen_ids)
                
                elif not first_run:
                    if int(time.time()) % 60 == 0:
                        log.info(f"💓 Surveillance active - {len(seen_ids)} alertes traitées")
                
                first_run = False
                
        except requests.exceptions.ConnectionError:
            consecutive_errors += 1
            if consecutive_errors == 1:
                log.warning(f"⚠️ API inaccessible ({api_base})")
            elif consecutive_errors % 10 == 0:
                log.warning(f"⚠️ API toujours inaccessible - {consecutive_errors} erreurs")
        except Exception as e:
            log.error(f"Erreur inattendue : {e}")
        
        if int(time.time()) % 300 == 0:
            save_state(seen_ids)
        
        time.sleep(interval)


# ════════════════════════════════════════════════════════════════════════════
#  MODE 2 — Surveillance directe en base (sans Flask)
# ════════════════════════════════════════════════════════════════════════════
def watch_db(interval: int, notifier: WindowsNotifier, email_notifier=None):
    try:
        import psycopg2
        import psycopg2.extras
        from psycopg2 import OperationalError
    except ImportError:
        log.error("psycopg2 introuvable. Lancez : pip install psycopg2-binary")
        sys.exit(1)
    
    db_cfg = get_db_config()
    
    log.info(f"Démarrage surveillance DB directe → {db_cfg['host']}:{db_cfg['port']}/{db_cfg['dbname']}")
    
    seen_ids, _ = load_state()
    first_run = len(seen_ids) == 0
    consecutive_failures = 0
    
    # Tester la connexion DB
    for i in range(3):
        try:
            test_conn = psycopg2.connect(**db_cfg, connect_timeout=5)
            test_conn.close()
            log.info(f"✅ Base de données accessible : {db_cfg['host']}/{db_cfg['dbname']}")
            break
        except OperationalError as e:
            if i < 2:
                log.warning(f"⏳ Attente DB... ({i+1}/3) : {e}")
                time.sleep(5)
            else:
                log.error(f"❌ Base de données injoignable : {e}")
                log.error("Vérifiez que PostgreSQL est lancé et les identifiants corrects")
                sys.exit(1)
    
    while True:
        try:
            conn = psycopg2.connect(**db_cfg, connect_timeout=5)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            cur.execute("""
                SELECT id, timestamp, source_ip, destination_ip,
                       source_port, destination_port,
                       attack_type, severity, protocol, details
                FROM alertes
                WHERE timestamp > NOW() - INTERVAL '%s seconds'
                ORDER BY timestamp DESC
                LIMIT 500
            """, (interval * 3,))
            
            rows = cur.fetchall()
            conn.close()
            consecutive_failures = 0
            
            new_rows = [r for r in rows if r["id"] not in seen_ids]
            
            if new_rows:
                log.info(f"📨 {len(new_rows)} nouvelle(s) alerte(s) détectée(s) dans la DB")
                
                for r in sorted(new_rows, key=lambda x: x.get("timestamp") or datetime.min):
                    seen_ids.add(r["id"])
                    
                    sev = normalize_severity(r["severity"])
                    
                    src_ip = r['source_ip'] or "0.0.0.0"
                    src_port = r['source_port']
                    dst_ip = r['destination_ip'] or "0.0.0.0"
                    dst_port = r['destination_port']
                    
                    src = f"{src_ip}:{src_port}" if src_port else src_ip
                    dst = f"{dst_ip}:{dst_port}" if dst_port else dst_ip
                    
                    alert = {
                        "id": r["id"],
                        "name": r["attack_type"] or "Attaque inconnue",
                        "severity": sev,
                        "src": src,
                        "dst": dst,
                        "proto": r["protocol"] or "N/A",
                        "timestamp": r["timestamp"].isoformat() if r["timestamp"] else "",
                        "details": r.get("details", {})
                    }
                    
                    if sev == "critical":
                        threading.Thread(target=play_alert_sound, args=("critical",), daemon=True).start()
                    
                    threading.Thread(target=_handle_new_alert, args=(alert, notifier, email_notifier), daemon=True).start()
                    
                    if len(seen_ids) % 10 == 0:
                        save_state(seen_ids)
            
            elif not first_run:
                if int(time.time()) % 60 == 0:
                    log.info(f"💓 Surveillance active - {len(seen_ids)} alertes en base")
            
            first_run = False
            save_state(seen_ids)
            
        except OperationalError as e:
            consecutive_failures += 1
            if consecutive_failures == 1:
                log.warning(f"⚠️ Connexion DB perdue : {e}")
            elif consecutive_failures % 5 == 0:
                log.warning(f"⚠️ DB toujours inaccessible ({consecutive_failures} erreurs)")
        except Exception as e:
            log.error(f"Erreur DB inattendue : {e}")
        
        time.sleep(interval)


# ════════════════════════════════════════════════════════════════════════════
#  Traitement d'une nouvelle alerte
# ════════════════════════════════════════════════════════════════════════════
# Couleurs console
SEV_COLOR = {
    "critical": "\033[91m",
    "medium":   "\033[93m",
    "low":      "\033[92m",
}
RESET = "\033[0m"

SEV_LABEL = {
    "critical": "🔴 CRITIQUE",
    "medium":   "🟡 MOYEN",
    "low":      "🔵 FAIBLE",
}

def _handle_new_alert(alert: dict, notifier: WindowsNotifier, email_notifier=None):
    sev = normalize_severity(alert.get("severity", "low"))
    name = alert.get("name", "Alerte inconnue")
    src = alert.get("src", "?")
    dst = alert.get("dst", "?")
    proto = alert.get("proto", "N/A")
    ts = alert.get("timestamp", "")
    
    color = SEV_COLOR.get(sev, "")
    label = SEV_LABEL.get(sev, sev.upper())
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    log.info(f"{color}[{timestamp}] ⚠ {label} | {name} | {src} → {dst} ({proto}){RESET}")
    
    # Préparer la notification Windows
    icons = {
        "critical": "⚠️🚨",
        "medium": "⚠️",
        "low": "ℹ️"
    }
    
    title = f"{icons.get(sev, '🔔')} IDS - {label}"
    
    message_lines = [
        f"📋 {name}",
        f"📡 {src} → {dst} [{proto}]"
    ]
    
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            message_lines.append(f"🕐 {dt.strftime('%H:%M:%S')}")
        except:
            pass
    
    details = alert.get("details")
    if details and isinstance(details, dict):
        if "payload" in details:
            message_lines.append(f"📦 Payload: {details['payload'][:50]}...")
        if "signature" in details:
            message_lines.append(f"🔍 Sig: {details['signature'][:40]}...")
    
    message = "\n".join(message_lines)
    
    def send():
        for attempt in range(2):
            if notifier.notify(title, message, sev):
                break
            if attempt == 0:
                time.sleep(0.5)
    
    threading.Thread(target=send, daemon=True).start()

    # Envoi de l'email aux admins
    if email_notifier:
        threading.Thread(target=email_notifier.send_alert_email, args=(alert,), daemon=True).start()
    
    # Pour les alertes critiques, écrire dans un fichier d'urgence
    if sev == "critical":
        try:
            with open(CONFIG_DIR / "critical_alerts.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} | {name} | {src} -> {dst}\n")
        except:
            pass


# ════════════════════════════════════════════════════════════════════════════
#  Point d'entrée
# ════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="IDS Windows Background Notifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api",
        default="http://localhost:5000",
        help="URL de base de l'API Flask (défaut: http://localhost:5000)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Intervalle de polling en secondes (défaut: 5)",
    )
    parser.add_argument(
        "--db",
        action="store_true",
        help="Mode connexion directe à la base (sans Flask)",
    )
    parser.add_argument(
        "--sound",
        action="store_true",
        default=True,
        help="Activer les sons d'alerte (défaut: activé)",
    )
    args = parser.parse_args()
    
    log.info("=" * 60)
    log.info("🛡️ IDS Background Notifier v2.0 - Démarrage")
    log.info(f"📁 Dossier config: {CONFIG_DIR}")
    log.info("=" * 60)
    
    notifier = WindowsNotifier()
    email_notifier = AdminEmailNotifier(get_db_config())
    
    # Afficher le statut de l'email
    if email_notifier.is_ready():
        log.info("✉️ Envoi email admin ACTIVÉ")
        # Test de connexion SMTP au démarrage
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((email_notifier.smtp_host, email_notifier.smtp_port))
            sock.close()
            if result == 0:
                log.info(f"   ✅ Serveur SMTP {email_notifier.smtp_host}:{email_notifier.smtp_port} accessible")
            else:
                log.warning(f"   ⚠️ Serveur SMTP {email_notifier.smtp_host}:{email_notifier.smtp_port} inaccessible")
        except:
            pass
    else:
        log.info("✉️ Envoi email admin DÉSACTIVÉ")
        log.info("   Pour activer: configurez SMTP dans %APPDATA%\\IDS_Notifier\\.env")
    
    try:
        if args.db:
            watch_db(args.interval, notifier, email_notifier)
        else:
            watch_api(args.api, args.interval, notifier, email_notifier)
    except KeyboardInterrupt:
        log.info("🛑 Notifier arrêté par l'utilisateur.")
        save_state(set())
        sys.exit(0)
    except Exception as e:
        log.error(f"💥 Erreur fatale: {e}")
        save_state(set())
        sys.exit(1)

if __name__ == "__main__":
    main()