"""
═════════════════════════════════════════════════════════════════════════════
    IDS ALERT NOTIFIER v3.0 - SUPABASE EDITION
    Notifications Windows toast + Email auto aux admins
    Aucune configuration manuelle requise
═════════════════════════════════════════════════════════════════════════════
"""

import argparse
import sys
import time
import logging
import threading
import os
import json
import smtplib
import socket
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from urllib.parse import urlparse

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════
CONFIG_DIR = Path(os.getenv("APPDATA")) / "IDS_Notifier"
CONFIG_DIR.mkdir(exist_ok=True)
STATE_FILE = CONFIG_DIR / "notifier_state.json"
LOG_FILE = CONFIG_DIR / "notifier.log"
EMAIL_CONFIG_FILE = CONFIG_DIR / "email_config.json"

# ────────────────────────────────────────────────────────────────────────────
# LOGGING
# ────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ids-notifier")


def load_env():
    """Charge les variables d'environnement depuis .env"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
            log.info("✓ Variables d'environnement chargées depuis .env")
        except Exception as e:
            log.warning(f"⚠ Impossible de charger .env: {e}")


def parse_db_url(url):
    """Parse une URL PostgreSQL Supabase"""
    import urllib.parse
    parsed = urlparse(url)
    return {
        "dbname": parsed.path.lstrip("/") or "postgres",
        "user": urllib.parse.unquote(parsed.username) if parsed.username else None,
        "password": urllib.parse.unquote(parsed.password) if parsed.password else None,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
    }


def get_db_config():
    """Récupère la configuration DB depuis .env"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("❌ DATABASE_URL non trouvée dans .env")
        sys.exit(1)
    return parse_db_url(db_url)


# ════════════════════════════════════════════════════════════════════════════
# GESTION D'ÉTAT
# ════════════════════════════════════════════════════════════════════════════
def load_state():
    """Charge les alertes déjà vues"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                return set(state.get("seen_ids", [])), state.get("last_check", 0)
        except:
            pass
    return set(), 0


def save_state(seen_ids):
    """Sauvegarde les alertes vues"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"seen_ids": list(seen_ids), "last_check": time.time()}, f)
    except Exception as e:
        log.error(f"❌ Erreur sauvegarde état: {e}")


# ════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS EMAIL AUX ADMINS
# ════════════════════════════════════════════════════════════════════════════
class AdminEmailNotifier:
    """Envoie les alertes par email aux admin/security_admin"""

    def __init__(self, db_cfg):
        self.db_cfg = db_cfg
        self.sent_alert_ids = set()
        self._lock = threading.Lock()
        self._load_config()

    def _load_config(self):
        """Charge la configuration SMTP"""
        try:
            if EMAIL_CONFIG_FILE.exists():
                with open(EMAIL_CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.smtp_host = config.get("smtp_server", "")
                self.smtp_port = int(config.get("smtp_port", 587))
                self.smtp_user = config.get("smtp_user", "")
                self.smtp_password = config.get("smtp_password", "")
                self.smtp_from = config.get("from_email", "")
                self.use_tls = config.get("use_tls", True)
                self.use_ssl = config.get("use_ssl", False)
                self.enabled = bool(self.smtp_host and self.smtp_from)
            else:
                self.enabled = False
        except Exception as e:
            log.warning(f"⚠ Erreur chargement email config: {e}")
            self.enabled = False

    def is_ready(self):
        """Vérifie si le SMTP est configuré"""
        return self.enabled

    def _fetch_admin_emails(self):
        """Récupère les emails des admins"""
        try:
            import psycopg2
        except ImportError:
            log.error("❌ psycopg2 introuvable")
            return []

        conn = None
        try:
            conn = psycopg2.connect(**self.db_cfg, connect_timeout=5, sslmode="require")
            cur = conn.cursor()
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
            return emails
        except Exception as exc:
            log.error(f"❌ Erreur récupération emails: {exc}")
            return []
        finally:
            if conn:
                conn.close()

    def _build_email_body(self, alert):
        """Construit le corps de l'email"""
        ts = alert.get("timestamp", "N/A")
        details = alert.get("details", {})
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except:
                pass

        severity = alert.get("severity", "low").upper()
        severity_emoji = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🔵",
        }.get(severity, "ℹ️")

        body = f"""
═══════════════════════════════════════════════════════════════════════════
    {severity_emoji} ALERTE IDS DÉTECTÉE {severity_emoji}
═══════════════════════════════════════════════════════════════════════════

🆔 ID ALERTE    : {alert.get('id', 'N/A')}
📋 TYPE         : {alert.get('name', 'Alerte inconnue')}
⚠️  SÉVÉRITÉ    : {severity}
🕐 HORODATAGE   : {ts}

📡 SOURCE       : {alert.get('src', '?')}
🎯 DESTINATION  : {alert.get('dst', '?')}
🔌 PROTOCOLE    : {alert.get('proto', 'N/A')}

═══════════════════════════════════════════════════════════════════════════
DÉTAILS SUPPLÉMENTAIRES :
───────────────────────────────────────────────────────────────────────────
{json.dumps(details, ensure_ascii=False, indent=2)}

═══════════════════════════════════════════════════════════════════════════
⚠️  ACTION RECOMMANDÉE: Vérifiez immédiatement cette alerte
═══════════════════════════════════════════════════════════════════════════

Generated by IDS Notifier v3.0
"""
        return body

    def _send_message(self, recipient, subject, body):
        """Envoie un email"""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.smtp_from
            msg["To"] = recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            if self.use_ssl:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                    if self.smtp_user:
                        server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.ehlo()
                    if self.use_tls:
                        server.starttls()
                        server.ehlo()
                    if self.smtp_user:
                        server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)

            log.info(f"✓ Email envoyé à {recipient}")
            return True
        except Exception as exc:
            log.error(f"❌ Erreur envoi email à {recipient}: {exc}")
            return False

    def send_alert_email(self, alert):
        """Envoie l'alerte par email"""
        alert_id = alert.get("id")
        with self._lock:
            if alert_id in self.sent_alert_ids:
                return
            self.sent_alert_ids.add(alert_id)
            if len(self.sent_alert_ids) > 1000:
                self.sent_alert_ids = set(list(self.sent_alert_ids)[-500:])

        if not self.is_ready():
            log.debug("📧 Email désactivé")
            return

        recipients = self._fetch_admin_emails()
        if not recipients:
            log.warning("⚠ Aucun email admin trouvé")
            return

        severity = alert.get("severity", "low").upper()
        subject = f"[IDS ALERT] {severity} - {alert.get('name', 'Unknown')}"
        body = self._build_email_body(alert)

        log.info(f"📧 Envoi email à {len(recipients)} admin(s)...")
        for recipient in recipients:
            threading.Thread(
                target=self._send_message,
                args=(recipient, subject, body),
                daemon=True
            ).start()


# ════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS WINDOWS
# ════════════════════════════════════════════════════════════════════════════
class WindowsNotifier:
    """Affiche des notifications Windows toast"""

    def __init__(self):
        self.last_toast_time = {}

    def notify(self, title, message, severity="normal"):
        """Envoie une notification"""
        current_time = time.time()
        if title in self.last_toast_time:
            if current_time - self.last_toast_time[title] < 2:
                return

        methods = [
            self._notify_winrt,
            self._notify_win10toast,
            self._notify_winotify,
            self._notify_messagebox,
        ]

        for method in methods:
            try:
                if method(title, message, severity):
                    self.last_toast_time[title] = current_time
                    return True
            except:
                continue

        return False

    def _notify_winrt(self, title, message, severity="normal"):
        """Utilise Windows.Runtime (winrt)"""
        try:
            from winrt.windows.ui.notifications import (
                ToastNotificationManager,
                ToastNotification,
                ToastTemplateType,
                ToastDuration,
            )
            from winrt.windows.data.xml.dom import XmlDocument

            template = ToastTemplateType.TOAST_TEXT02
            toast_xml = ToastNotificationManager.get_template_content(template)
            xml_doc = XmlDocument()
            xml_doc.load_xml(toast_xml)
            text_nodes = xml_doc.get_elements_by_tag_name("text")
            text_nodes[0].append_child(xml_doc.create_text_node(title[:64]))
            text_nodes[1].append_child(xml_doc.create_text_node(message[:256]))

            duration = (
                ToastDuration.LONG if severity == "critical" else ToastDuration.SHORT
            )
            toast = ToastNotification(xml_doc)
            toast.expiration_time = datetime.now() + timedelta(seconds=30)

            notifier = ToastNotificationManager.create_toast_notifier("IDS Monitor")
            notifier.show(toast)
            return True
        except:
            return False

    def _notify_win10toast(self, title, message, severity="normal"):
        """Utilise win10toast-persist"""
        try:
            from win10toast_persist import ToastNotifier

            duration = 10 if severity == "critical" else 6
            toaster = ToastNotifier()
            toaster.show_toast(title[:64], message[:256], duration=duration, threaded=True)
            return True
        except:
            return False

    def _notify_winotify(self, title, message, severity="normal"):
        """Utilise winotify"""
        try:
            from winotify import Notification

            notif = Notification(
                app_id="IDS Monitor",
                title=title[:64],
                msg=message[:256],
                duration="long" if severity == "critical" else "short",
            )
            notif.show()
            return True
        except:
            return False

    def _notify_messagebox(self, title, message, severity="normal"):
        """Fallback: MessageBox"""
        try:
            import ctypes

            flags = 0x40 | 0x40000
            if severity == "critical":
                flags = 0x30 | 0x40000
            ctypes.windll.user32.MessageBoxW(0, message[:256], title[:64], flags)
            return True
        except:
            return False


def play_alert_sound(severity="normal"):
    """Joue un son d'alerte"""
    try:
        import winsound

        sounds = {
            "critical": (1000, 500),
            "medium": (800, 300),
            "low": (600, 200),
        }
        freq, duration = sounds.get(severity, (500, 150))
        winsound.Beep(freq, duration)
    except:
        pass


# ════════════════════════════════════════════════════════════════════════════
# SURVEILLANCE SUPABASE
# ════════════════════════════════════════════════════════════════════════════
def watch_database(interval: int, notifier: WindowsNotifier, email_notifier=None):
    """Surveille les alertes en base de données Supabase"""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        log.error("❌ psycopg2 introuvable: pip install psycopg2-binary")
        sys.exit(1)

    db_cfg = get_db_config()
    log.info(f"🔍 Surveillance Supabase → {db_cfg['host']}/{db_cfg['dbname']}")

    seen_ids, _ = load_state()
    first_run = len(seen_ids) == 0
    consecutive_failures = 0

    # Test connexion
    for i in range(3):
        try:
            conn = psycopg2.connect(**db_cfg, sslmode="require", connect_timeout=5)
            conn.close()
            log.info(f"✅ Supabase accessible")
            break
        except Exception as e:
            if i < 2:
                log.warning(f"⏳ Attente Supabase ({i + 1}/3)...")
                time.sleep(3)
            else:
                log.error(f"❌ Supabase inaccessible: {e}")
                sys.exit(1)

    while True:
        try:
            conn = psycopg2.connect(**db_cfg, sslmode="require", connect_timeout=5)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Récupère les alertes récentes
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
                log.info(f"📨 {len(new_rows)} alerte(s) détectée(s)")

                for r in sorted(new_rows, key=lambda x: x.get("timestamp") or datetime.min):
                    seen_ids.add(r["id"])

                    severity = (r["severity"] or "low").lower()
                    src = f"{r['source_ip']}:{r['source_port']}" if r["source_port"] else r["source_ip"] or "0.0.0.0"
                    dst = f"{r['destination_ip']}:{r['destination_port']}" if r["destination_port"] else r["destination_ip"] or "0.0.0.0"

                    alert = {
                        "id": r["id"],
                        "name": r["attack_type"] or "Alerte inconnue",
                        "severity": severity,
                        "src": src,
                        "dst": dst,
                        "proto": r["protocol"] or "N/A",
                        "timestamp": r["timestamp"].isoformat() if r["timestamp"] else "",
                        "details": r.get("details", {}),
                    }

                    if severity == "critical":
                        threading.Thread(
                            target=play_alert_sound,
                            args=("critical",),
                            daemon=True,
                        ).start()

                    _handle_new_alert(alert, notifier, email_notifier)

                    if len(seen_ids) % 10 == 0:
                        save_state(seen_ids)

            elif not first_run and int(time.time()) % 60 == 0:
                log.info(f"💓 Surveillance active - {len(seen_ids)} alertes traitées")

            first_run = False
            save_state(seen_ids)

        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures == 1:
                log.warning(f"⚠️ Erreur Supabase: {e}")
            elif consecutive_failures % 5 == 0:
                log.warning(f"⚠️ Supabase inaccessible ({consecutive_failures}x)")

        time.sleep(interval)


# ════════════════════════════════════════════════════════════════════════════
# TRAITEMENT DES ALERTES
# ════════════════════════════════════════════════════════════════════════════
def _handle_new_alert(alert: dict, notifier: WindowsNotifier, email_notifier=None):
    """Traite une nouvelle alerte"""
    severity = (alert.get("severity", "low") or "low").lower()
    name = alert.get("name", "Alerte inconnue")
    src = alert.get("src", "?")
    dst = alert.get("dst", "?")
    proto = alert.get("proto", "N/A")

    icons = {
        "critical": "🔴 CRITIQUE",
        "medium": "🟡 MOYEN",
        "low": "🔵 FAIBLE",
    }

    label = icons.get(severity, "ℹ️ INFO")
    timestamp = datetime.now().strftime("%H:%M:%S")
    log.info(f"[{timestamp}] ⚠️ {label} | {name} | {src} → {dst}")

    title = f"🚨 IDS Alert - {label}"
    message = f"{name}\n{src} → {dst}\n{proto}"

    # Notification Windows
    notifier.notify(title, message, severity)

    # Email aux admins
    if email_notifier:
        threading.Thread(
            target=email_notifier.send_alert_email,
            args=(alert,),
            daemon=True,
        ).start()


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="IDS Alert Notifier v3.0")
    parser.add_argument("--interval", type=int, default=5, help="Intervalle polling (sec)")
    args = parser.parse_args()

    log.info("=" * 80)
    log.info("🛡️ IDS ALERT NOTIFIER v3.0 - DÉMARRAGE")
    log.info(f"📁 Config: {CONFIG_DIR}")
    log.info("=" * 80)

    load_env()

    notifier = WindowsNotifier()
    db_cfg = get_db_config()
    email_notifier = AdminEmailNotifier(db_cfg)

    if email_notifier.is_ready():
        log.info("✉️ Email admin: ACTIVÉ")
        # Test SMTP
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((email_notifier.smtp_host, email_notifier.smtp_port))
            sock.close()
            if result == 0:
                log.info(f"   ✓ SMTP {email_notifier.smtp_host}:{email_notifier.smtp_port} OK")
            else:
                log.warning(f"   ⚠️ SMTP {email_notifier.smtp_host}:{email_notifier.smtp_port} inaccessible")
        except:
            pass
    else:
        log.warning("⚠️ Email admin: DÉSACTIVÉ")

    try:
        watch_database(args.interval, notifier, email_notifier)
    except KeyboardInterrupt:
        log.info("🛑 Arrêt demandé")
        save_state(set())
        sys.exit(0)
    except Exception as e:
        log.error(f"❌ Erreur fatale: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
