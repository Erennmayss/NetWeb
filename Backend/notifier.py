"""
IDS Alert Notifier - Surveillance en arrière-plan (Windows)
============================================================
Deux sources de détection (en parallèle) :
  1. DB directe  : poll PostgreSQL → nouvelles lignes dans la table alertes
  2. Flask INSERT : écoute les POST sur /api/insert/ envoyés par l'IDS

Dépendances :
    pip install plyer requests psycopg2-binary win10toast-persist winotify winrt

Usage :
    python notifier.py
    python notifier.py --api http://localhost:5000
    python notifier.py --interval 5
    python notifier.py --db          (DB uniquement, sans Flask)
    python notifier.py --flask-only  (Flask uniquement, sans DB)
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
STATE_FILE  = CONFIG_DIR / "notifier_state.json"
LOG_FILE    = CONFIG_DIR / "notifier.log"


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
                    key   = key.strip()
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
                "smtp_server":   "SMTP_HOST",
                "smtp_port":     "SMTP_PORT",
                "smtp_user":     "SMTP_USER",
                "smtp_password": "SMTP_PASSWORD",
                "use_tls":       "SMTP_USE_TLS",
                "from_email":    "SMTP_FROM",
            }
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


# ── État persistant ─────────────────────────────────────────────────────────
def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                return set(state.get("seen_ids", [])), state.get("last_check", 0)
        except:
            pass
    return set(), 0


def save_state(seen_ids):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"seen_ids": list(seen_ids), "last_check": time.time()}, f)
    except Exception as e:
        log.error(f"Erreur sauvegarde état: {e}")


# ── Helpers ─────────────────────────────────────────────────────────────────
def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "oui"}


def get_db_config():
    return {
        "dbname":   os.getenv("DB_NAME",     "ids_db"),
        "user":     os.getenv("DB_USER",     "aya"),
        "password": os.getenv("DB_PASSWORD", "aya"),
        "host":     os.getenv("DB_HOST",     "192.168.1.2"),
        "port":     os.getenv("DB_PORT",     "5432"),
    }


def normalize_severity(value):
    sev_raw = (value or "").lower()
    if sev_raw in ("critical", "critique", "high", "élevée", "elevee"):
        return "critical"
    if sev_raw in ("medium", "moyen", "moyenne"):
        return "medium"
    return "low"


# ════════════════════════════════════════════════════════════════════════════
#  NOTIFICATIONS EMAIL POUR LES ADMINS
# ════════════════════════════════════════════════════════════════════════════
class AdminEmailNotifier:
    def __init__(self, db_cfg):
        self.db_cfg        = db_cfg
        self.enabled       = parse_bool(os.getenv("SMTP_ENABLED"), default=False)
        self.smtp_host     = os.getenv("SMTP_HOST", "").strip()
        self.smtp_port     = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user     = os.getenv("SMTP_USER", "").strip()
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from     = os.getenv("SMTP_FROM", "").strip()
        self.use_tls       = parse_bool(os.getenv("SMTP_USE_TLS"), default=True)
        self.use_ssl       = parse_bool(os.getenv("SMTP_USE_SSL"), default=False)
        self.subject_prefix = os.getenv("SMTP_SUBJECT_PREFIX", "[IDS]")
        if "gmail.com" in self.smtp_host.lower():
            self.smtp_password = self.smtp_password.replace(" ", "")
        self._sent_alert_ids = set()
        self._lock = threading.Lock()

    def is_ready(self):
        return self.enabled and bool(self.smtp_host and self.smtp_from)

    def _fetch_admin_emails(self):
        try:
            import psycopg2
        except ImportError:
            log.error("psycopg2 introuvable: impossible de récupérer les emails admin")
            return []
        conn = None
        try:
            conn = psycopg2.connect(**self.db_cfg, connect_timeout=5)
            cur  = conn.cursor()
            cur.execute("""
                SELECT DISTINCT TRIM(email)
                FROM utilisateur
                WHERE LOWER(TRIM(role)) IN ('admin', 'security_admin')
                  AND email IS NOT NULL
                  AND TRIM(email) <> ''
            """)
            emails = [row[0] for row in cur.fetchall() if row[0]]
            if emails:
                log.info(f"📧 {len(emails)} email(s) admin trouvé(s)")
            else:
                log.warning("⚠️ Aucun email admin/security_admin trouvé dans la table utilisateur")
            return emails
        except Exception as exc:
            log.error(f"Impossible de récupérer les emails admin: {exc}")
            return []
        finally:
            if conn:
                conn.close()

    def _build_subject(self, alert):
        severity_labels = {"critical": "CRITIQUE", "medium": "MOYENNE", "low": "FAIBLE"}
        sev   = normalize_severity(alert.get("severity"))
        label = severity_labels.get(sev, sev.upper())
        name  = alert.get("name", "Alerte inconnue")
        return f"{self.subject_prefix} Alerte {label} - {name}"

    def _build_body(self, alert):
        ts      = alert.get("timestamp") or datetime.now().isoformat()
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
        message = EmailMessage()
        message["From"]    = self.smtp_from
        message["To"]      = recipient
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
        alert_id = alert.get("id")
        with self._lock:
            if alert_id in self._sent_alert_ids:
                return
            self._sent_alert_ids.add(alert_id)
            if len(self._sent_alert_ids) > 1000:
                self._sent_alert_ids = set(list(self._sent_alert_ids)[-500:])

        if not self.is_ready():
            return

        recipients = self._fetch_admin_emails()
        if not recipients:
            return

        subject = self._build_subject(alert)
        body    = self._build_body(alert)
        log.info(f"📧 Envoi alerte à {len(recipients)} admin(s)...")
        success = 0
        for r in recipients:
            if self._send_message(r, subject, body):
                success += 1
                log.info(f"   ✓ Email envoyé à {r}")
        log.info(f"✅ {success}/{len(recipients)} email(s) envoyé(s)")


# ════════════════════════════════════════════════════════════════════════════
#  NOTIFICATION WINDOWS (multi-méthodes)
# ════════════════════════════════════════════════════════════════════════════
class WindowsNotifier:
    def __init__(self):
        self.last_toast_time = {}

    def _notify_winrt(self, title, message, severity="normal"):
        try:
            from winrt.windows.ui.notifications import (
                ToastNotificationManager, ToastNotification,
                ToastTemplateType, ToastDuration,
            )
            from winrt.windows.data.xml.dom import XmlDocument
            template  = ToastTemplateType.TOAST_TEXT02
            toast_xml = ToastNotificationManager.get_template_content(template)
            xml_doc   = XmlDocument()
            xml_doc.load_xml(toast_xml)
            nodes = xml_doc.get_elements_by_tag_name("text")
            nodes[0].append_child(xml_doc.create_text_node(title))
            nodes[1].append_child(xml_doc.create_text_node(message))
            duration = ToastDuration.LONG if severity == "critical" else ToastDuration.SHORT
            toast = ToastNotification(xml_doc)
            toast.expiration_time = datetime.now() + timedelta(seconds=30)
            ToastNotificationManager.create_toast_notifier("IDS Monitor").show(toast)
            return True
        except Exception as e:
            log.debug(f"WinRT failed: {e}")
            return False

    def _notify_win10toast(self, title, message, severity="normal"):
        try:
            from win10toast_persist import ToastNotifier
            duration  = 10 if severity == "critical" else 6
            icon_path = Path(__file__).parent / "icon.ico"
            icon      = str(icon_path) if icon_path.exists() else None
            ToastNotifier().show_toast(title, message, icon_path=icon, duration=duration, threaded=True)
            return True
        except Exception as e:
            log.debug(f"win10toast failed: {e}")
            return False

    def _notify_plyer(self, title, message, severity="normal"):
        try:
            from plyer import notification
            notification.notify(title=title[:64], message=message[:256],
                                app_name="IDS Monitor", timeout=8)
            return True
        except Exception as e:
            log.debug(f"Plyer failed: {e}")
            return False

    def _notify_winotify(self, title, message, severity="normal"):
        try:
            from winotify import Notification, audio
            notif = Notification(app_id="IDS Monitor", title=title[:64],
                                 msg=message[:256],
                                 duration="long" if severity == "critical" else "short")
            if severity == "critical":
                notif.set_audio(audio.Default, loop=False)
            notif.show()
            return True
        except Exception as e:
            log.debug(f"Winotify failed: {e}")
            return False

    def _notify_messagebox(self, title, message, severity="normal"):
        try:
            import ctypes
            flags = 0x30 | 0x40000 if severity == "critical" else 0x40 | 0x40000
            ctypes.windll.user32.MessageBoxW(0, message[:256], title[:64], flags)
            return True
        except:
            return False

    def notify(self, title, message, severity="normal"):
        current_time = time.time()
        if title in self.last_toast_time:
            if current_time - self.last_toast_time[title] < 2:
                return False
        for method in [self._notify_winrt, self._notify_win10toast,
                       self._notify_winotify, self._notify_plyer,
                       self._notify_messagebox]:
            if method(title, message, severity):
                self.last_toast_time[title] = current_time
                return True
        log.error("Aucune méthode de notification n'a fonctionné")
        return False


# ── Son d'alerte ─────────────────────────────────────────────────────────────
def play_alert_sound(severity="normal"):
    try:
        import winsound
        sounds = {"critical": (1000, 500), "medium": (800, 300),
                  "low": (600, 200), "normal": (500, 150)}
        freq, duration = sounds.get(severity, (500, 150))
        winsound.Beep(freq, duration)
    except:
        pass


# ── Traitement d'une nouvelle alerte ─────────────────────────────────────────
SEV_COLOR = {"critical": "\033[91m", "medium": "\033[93m", "low": "\033[92m"}
SEV_LABEL = {"critical": "🔴 CRITIQUE", "medium": "🟡 MOYEN", "low": "🔵 FAIBLE"}
RESET     = "\033[0m"


def _handle_new_alert(alert: dict, notifier: WindowsNotifier, email_notifier=None):
    sev   = normalize_severity(alert.get("severity", "low"))
    name  = alert.get("name", "Alerte inconnue")
    src   = alert.get("src", "?")
    dst   = alert.get("dst", "?")
    proto = alert.get("proto", "N/A")
    ts    = alert.get("timestamp", "")

    color = SEV_COLOR.get(sev, "")
    label = SEV_LABEL.get(sev, sev.upper())
    timestamp = datetime.now().strftime("%H:%M:%S")
    log.info(f"{color}[{timestamp}] ⚠ {label} | {name} | {src} → {dst} ({proto}){RESET}")

    icons   = {"critical": "⚠️🚨", "medium": "⚠️", "low": "ℹ️"}
    title   = f"{icons.get(sev, '🔔')} IDS - {label}"
    lines   = [f"📋 {name}", f"📡 {src} → {dst} [{proto}]"]
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            lines.append(f"🕐 {dt.strftime('%H:%M:%S')}")
        except:
            pass
    details = alert.get("details")
    if details and isinstance(details, dict):
        if "payload" in details:
            lines.append(f"📦 {details['payload'][:50]}...")
        if "signature" in details:
            lines.append(f"🔍 {details['signature'][:40]}...")
    message = "\n".join(lines)

    def send():
        for attempt in range(2):
            if notifier.notify(title, message, sev):
                break
            if attempt == 0:
                time.sleep(0.5)
    threading.Thread(target=send, daemon=True).start()

    if email_notifier:
        threading.Thread(target=email_notifier.send_alert_email, args=(alert,), daemon=True).start()

    if sev == "critical":
        try:
            with open(CONFIG_DIR / "critical_alerts.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} | {name} | {src} -> {dst}\n")
        except:
            pass


# ════════════════════════════════════════════════════════════════════════════
#  SOURCE 1 — Surveillance DB directe (poll nouvelles lignes INSERT)
# ════════════════════════════════════════════════════════════════════════════
def watch_db(interval: int, notifier: WindowsNotifier, email_notifier=None,
             shared_seen: set = None, shared_lock: threading.Lock = None):
    """
    Poll la table alertes toutes les `interval` secondes.
    Seules les lignes dont l'ID n'est pas encore connu déclenchent une notification.
    Aucune écriture n'est faite dans la base.
    """
    try:
        import psycopg2
        import psycopg2.extras
        from psycopg2 import OperationalError
    except ImportError:
        log.error("psycopg2 introuvable. Lancez : pip install psycopg2-binary")
        sys.exit(1)

    db_cfg = get_db_config()
    log.info(f"[DB]  Surveillance → {db_cfg['host']}:{db_cfg['port']}/{db_cfg['dbname']}")

    seen_ids, _ = load_state()
    # En mode dual on partage le set d'IDs déjà vus
    use_shared  = shared_seen is not None and shared_lock is not None
    consecutive_failures = 0
    first_run   = True

    while True:
        try:
            conn = psycopg2.connect(**db_cfg, connect_timeout=5)
            cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT id, timestamp, source_ip, destination_ip,
                       source_port, destination_port,
                       attack_type, severity, protocol, details
                FROM alertes
                WHERE timestamp > NOW() - INTERVAL %s
                ORDER BY timestamp DESC
                LIMIT 500
            """, (f"{interval * 3} seconds",))
            rows = cur.fetchall()
            conn.close()
            consecutive_failures = 0

            for r in rows:
                aid = r["id"]
                # Vérifier dans le set local et éventuellement partagé
                if use_shared:
                    with shared_lock:
                        if aid in shared_seen:
                            continue
                        shared_seen.add(aid)
                else:
                    if aid in seen_ids:
                        continue
                    seen_ids.add(aid)

                if first_run:
                    # Premier passage : mémoriser sans notifier
                    continue

                sev      = normalize_severity(r["severity"])
                src_ip   = r["source_ip"]  or "0.0.0.0"
                dst_ip   = r["destination_ip"] or "0.0.0.0"
                src_port = r["source_port"]
                dst_port = r["destination_port"]
                alert = {
                    "id":        aid,
                    "name":      r["attack_type"] or "Attaque inconnue",
                    "severity":  sev,
                    "src":       f"{src_ip}:{src_port}" if src_port else src_ip,
                    "dst":       f"{dst_ip}:{dst_port}" if dst_port else dst_ip,
                    "proto":     r["protocol"] or "N/A",
                    "timestamp": r["timestamp"].isoformat() if r["timestamp"] else "",
                    "details":   r.get("details", {}),
                }
                if sev == "critical":
                    threading.Thread(target=play_alert_sound, args=("critical",), daemon=True).start()
                threading.Thread(target=_handle_new_alert,
                                 args=(alert, notifier, email_notifier), daemon=True).start()

            if first_run:
                log.info(f"[DB]  {len(rows)} alertes existantes mémorisées (sans notification)")
                first_run = False
                if not use_shared:
                    save_state(seen_ids)

        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures == 1 or consecutive_failures % 5 == 0:
                log.warning(f"[DB]  Erreur ({consecutive_failures}): {e}")

        if not use_shared and len(seen_ids) % 20 == 0:
            save_state(seen_ids)

        time.sleep(interval)


# ════════════════════════════════════════════════════════════════════════════
#  SOURCE 2 — Réception Flask via POST /api/insert/
# ════════════════════════════════════════════════════════════════════════════
def watch_flask_insert(api_base: str, interval: int, notifier: WindowsNotifier,
                       email_notifier=None,
                       shared_seen: set = None, shared_lock: threading.Lock = None):
    """
    Interroge Flask pour récupérer les alertes récemment insérées via /api/insert/.
    L'endpoint doit retourner les alertes créées depuis le dernier appel.
    Format attendu : POST ou GET /api/insert/ → {"success": true, "alerts": [...]}
    """
    import requests

    log.info(f"[Flask] Surveillance INSERT → {api_base}/api/insert/  (toutes les {interval}s)")

    use_shared = shared_seen is not None and shared_lock is not None
    seen_ids, _ = load_state() if not use_shared else (set(), 0)
    first_run  = True

    # Attendre que Flask soit accessible (max 30s)
    for i in range(10):
        try:
            requests.get(f"{api_base}/api/health", timeout=3)
            log.info(f"[Flask] ✅ Accessible : {api_base}")
            break
        except Exception:
            if i < 9:
                log.warning(f"[Flask] ⏳ Pas encore prêt... ({i+1}/10)")
                time.sleep(3)
            else:
                log.warning(f"[Flask] ⚠️ Inaccessible après 30s — thread Flask en veille")

    # Paramètre "since" pour ne demander que les nouvelles alertes
    last_ts = datetime.utcnow().isoformat()

    consecutive_errors = 0
    while True:
        try:
            resp = requests.get(
                f"{api_base}/api/insert/",
                params={"since": last_ts, "limit": 200},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            consecutive_errors = 0

            if data.get("success"):
                alerts = data.get("alerts", [])
                if alerts:
                    log.info(f"[Flask] {len(alerts)} nouvelle(s) alerte(s) reçue(s) via /api/insert/")
                last_ts = datetime.utcnow().isoformat()

                for a in alerts:
                    aid = a.get("id")
                    if use_shared:
                        with shared_lock:
                            if aid in shared_seen:
                                continue
                            shared_seen.add(aid)
                    else:
                        if aid in seen_ids:
                            continue
                        seen_ids.add(aid)

                    if first_run:
                        continue  # Premier passage sans notification

                    sev = normalize_severity(a.get("severity", "low"))
                    if sev == "critical":
                        threading.Thread(target=play_alert_sound, args=("critical",), daemon=True).start()
                    # Normaliser le format si nécessaire
                    alert = {
                        "id":        aid,
                        "name":      a.get("attack_type") or a.get("name") or "Attaque inconnue",
                        "severity":  sev,
                        "src":       a.get("src") or a.get("source_ip", "?"),
                        "dst":       a.get("dst") or a.get("destination_ip", "?"),
                        "proto":     a.get("proto") or a.get("protocol", "N/A"),
                        "timestamp": a.get("timestamp", ""),
                        "details":   a.get("details", {}),
                    }
                    threading.Thread(target=_handle_new_alert,
                                     args=(alert, notifier, email_notifier), daemon=True).start()

                if first_run:
                    first_run = False

        except requests.exceptions.ConnectionError:
            consecutive_errors += 1
            if consecutive_errors == 1 or consecutive_errors % 12 == 0:
                log.warning(f"[Flask] ⚠️ Inaccessible ({api_base})")
        except Exception as e:
            log.error(f"[Flask] Erreur : {e}")

        time.sleep(interval)


# ════════════════════════════════════════════════════════════════════════════
#  Point d'entrée
# ════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="IDS Windows Background Notifier")
    parser.add_argument("--api",        default="http://127.0.0.1:5000",
                        help="URL Flask (défaut: http://127.0.0.1:5000)")
    parser.add_argument("--interval",   type=int, default=5,
                        help="Intervalle de polling en secondes (défaut: 5)")
    parser.add_argument("--db",         action="store_true",
                        help="Mode DB uniquement (sans Flask)")
    parser.add_argument("--flask-only", action="store_true",
                        help="Mode Flask /api/insert/ uniquement (sans DB directe)")
    parser.add_argument("--sound",      action="store_true", default=True,
                        help="Activer les sons d'alerte (défaut: activé)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("🛡️ IDS Background Notifier v2.1 - Démarrage")
    log.info(f"📁 Config: {CONFIG_DIR}")
    log.info("=" * 60)

    notifier       = WindowsNotifier()
    email_notifier = AdminEmailNotifier(get_db_config())

    if email_notifier.is_ready():
        log.info(f"✉️  Email admin ACTIVÉ → {email_notifier.smtp_host}:{email_notifier.smtp_port}")
    else:
        log.info("✉️  Email admin DÉSACTIVÉ (option 8 dans p.bat pour configurer)")

    try:
        # ── Mode DB uniquement ────────────────────────────────────────────
        if args.db and not getattr(args, "flask_only", False):
            log.info("▶ Mode : DB directe uniquement")
            watch_db(args.interval, notifier, email_notifier)

        # ── Mode Flask /api/insert/ uniquement ────────────────────────────
        elif getattr(args, "flask_only", False):
            log.info(f"▶ Mode : Flask /api/insert/ uniquement → {args.api}")
            watch_flask_insert(args.api, args.interval, notifier, email_notifier)

        # ── Mode par défaut : DB + Flask en parallèle ─────────────────────
        else:
            log.info(f"▶ Mode : DB directe  +  Flask /api/insert/ [{args.api}]  [parallèle]")
            log.info("   Les deux sources sont surveillées simultanément.")
            log.info("   Les doublons sont filtrés automatiquement par ID d'alerte.")

            shared_seen  = set()
            shared_lock  = threading.Lock()

            t_db = threading.Thread(
                target=watch_db,
                args=(args.interval, notifier, email_notifier, shared_seen, shared_lock),
                name="watcher-db",
                daemon=True,
            )
            t_flask = threading.Thread(
                target=watch_flask_insert,
                args=(args.api, args.interval, notifier, email_notifier, shared_seen, shared_lock),
                name="watcher-flask-insert",
                daemon=True,
            )
            t_db.start()
            t_flask.start()

            log.info("✅ Les deux watchers sont actifs. Ctrl+C pour arrêter.")
            while t_db.is_alive() or t_flask.is_alive():
                time.sleep(1)

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