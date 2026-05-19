"""
═════════════════════════════════════════════════════════════════════════════
    SNORT ALERT PROCESSOR - Integration avec IDS Notifier
    Récupère les alertes de Recuperation.py → Enregistre dans Supabase
    → Déclenche notifications Windows + Email
═════════════════════════════════════════════════════════════════════════════
"""

import os
import json
import logging
import threading
import smtplib
import socket
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from urllib.parse import urlparse

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════
CONFIG_DIR = Path(os.getenv("APPDATA")) / "IDS_Notifier"
CONFIG_DIR.mkdir(exist_ok=True)
LOG_FILE = CONFIG_DIR / "snort_processor.log"

# ────────────────────────────────────────────────────────────────────────────
# LOGGING
# ────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("snort-processor")


def load_env():
    """Charge les variables depuis .env"""
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
        except Exception as e:
            log.warning(f"⚠ Impossible de charger .env: {e}")


def parse_db_url(url):
    """Parse l'URL PostgreSQL Supabase"""
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
    """Récupère la config DB depuis .env"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("❌ DATABASE_URL non trouvée dans .env")
        return None
    return parse_db_url(db_url)


# ════════════════════════════════════════════════════════════════════════════
# ENREGISTREMENT DES ALERTES
# ════════════════════════════════════════════════════════════════════════════
class SnortAlertProcessor:
    """Traite et enregistre les alertes Snort"""

    def __init__(self):
        self.db_cfg = get_db_config()
        self.email_config = self._load_email_config()
        self.sent_alert_ids = set()
        self._lock = threading.Lock()

    def _load_email_config(self):
        """Charge la configuration SMTP"""
        email_config_file = CONFIG_DIR / "email_config.json"
        try:
            if email_config_file.exists():
                with open(email_config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"⚠ Erreur chargement email config: {e}")
        return {}

    def insert_alert(self, alert_data):
        """Insère une alerte dans Supabase"""
        if not self.db_cfg:
            log.error("❌ Configuration DB introuvable")
            return False

        try:
            import psycopg2
        except ImportError:
            log.error("❌ psycopg2 introuvable")
            return False

        try:
            conn = psycopg2.connect(**self.db_cfg, sslmode="require", connect_timeout=5)
            cur = conn.cursor()

            # Insérer l'alerte
            cur.execute("""
                INSERT INTO alertes 
                (timestamp, source_ip, destination_ip, source_port, destination_port,
                 protocol, attack_type, severity, details)
                VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                alert_data.get("source_ip", ""),
                alert_data.get("destination_ip", ""),
                alert_data.get("source_port"),
                alert_data.get("destination_port"),
                alert_data.get("protocol", ""),
                alert_data.get("attack_type", ""),
                alert_data.get("severity", "low"),
                json.dumps(alert_data.get("details", {})),
            ))

            alert_id = cur.fetchone()[0]
            conn.commit()
            conn.close()

            log.info(f"✓ Alerte enregistrée (ID: {alert_id})")

            # Envoyer les notifications
            threading.Thread(
                target=self._send_notifications,
                args=(alert_data, alert_id),
                daemon=True,
            ).start()

            return True

        except Exception as e:
            log.error(f"❌ Erreur insertion alerte: {e}")
            return False

    def _fetch_admin_emails(self):
        """Récupère les emails des admins"""
        if not self.db_cfg:
            return []

        try:
            import psycopg2
        except ImportError:
            return []

        try:
            conn = psycopg2.connect(**self.db_cfg, sslmode="require", connect_timeout=5)
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT TRIM(email)
                FROM utilisateur
                WHERE LOWER(TRIM(role)) IN ('admin', 'security_admin')
                  AND email IS NOT NULL
                  AND TRIM(email) <> ''
            """)
            emails = [row[0] for row in cur.fetchall() if row[0]]
            conn.close()
            return emails
        except Exception as e:
            log.warning(f"⚠ Erreur récupération emails: {e}")
            return []

    def _send_notifications(self, alert_data, alert_id):
        """Envoie les notifications (Windows + Email)"""
        alert_id_key = f"snort_{alert_id}"

        with self._lock:
            if alert_id_key in self.sent_alert_ids:
                return
            self.sent_alert_ids.add(alert_id_key)

        # Notification Windows
        self._notify_windows(alert_data)

        # Email aux admins
        if self.email_config.get("auto_enabled"):
            self._send_admin_email(alert_data)

    def _notify_windows(self, alert_data):
        """Affiche une notification Windows toast"""
        try:
            from winotify import Notification

            severity = (alert_data.get("severity", "low") or "low").lower()
            title = f"🚨 IDS Alert - {severity.upper()}"
            message = f"{alert_data.get('attack_type', 'Unknown')}\n"
            message += f"{alert_data.get('source_ip', '?')} → {alert_data.get('destination_ip', '?')}"

            notif = Notification(
                app_id="IDS Monitor",
                title=title[:64],
                msg=message[:256],
                duration="long" if severity == "critical" else "short",
            )
            notif.show()
            log.info("✓ Notification Windows envoyée")
        except Exception as e:
            log.debug(f"⚠ Notif Windows échouée: {e}")

    def _send_admin_email(self, alert_data):
        """Envoie l'alerte par email"""
        config = self.email_config
        if not config.get("smtp_server") or not config.get("from_email"):
            log.debug("📧 Email config incomplete")
            return

        recipients = self._fetch_admin_emails()
        if not recipients:
            log.warning("⚠ Aucun email admin trouvé")
            return

        subject = f"[IDS ALERT] {alert_data.get('severity', 'low').upper()} - {alert_data.get('attack_type', 'Unknown')}"
        body = self._build_email_body(alert_data)

        for recipient in recipients:
            threading.Thread(
                target=self._send_email,
                args=(recipient, subject, body, config),
                daemon=True,
            ).start()

    def _build_email_body(self, alert_data):
        """Construit le corps de l'email"""
        severity = (alert_data.get("severity", "low") or "low").upper()
        body = f"""
═══════════════════════════════════════════════════════════════════════════
    🚨 ALERTE IDS DÉTECTÉE 🚨
═══════════════════════════════════════════════════════════════════════════

📋 TYPE          : {alert_data.get('attack_type', 'Unknown')}
⚠️  SÉVÉRITÉ    : {severity}
🕐 HORODATAGE   : {datetime.now().isoformat()}

📡 SOURCE       : {alert_data.get('source_ip', '?')}
🎯 DESTINATION  : {alert_data.get('destination_ip', '?')}
🔌 PROTOCOLE    : {alert_data.get('protocol', 'N/A')}

═══════════════════════════════════════════════════════════════════════════
DÉTAILS :
───────────────────────────────────────────────────────────────────────────
{json.dumps(alert_data.get('details', {}), ensure_ascii=False, indent=2)}

═══════════════════════════════════════════════════════════════════════════
⚠️  ACTION RECOMMANDÉE: Vérifiez immédiatement cette alerte
═══════════════════════════════════════════════════════════════════════════

Generated by IDS Snort Processor
"""
        return body

    def _send_email(self, recipient, subject, body, config):
        """Envoie un email"""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = config.get("from_email", "")
            msg["To"] = recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            use_ssl = config.get("use_ssl", False)
            use_tls = config.get("use_tls", True)
            port = int(config.get("smtp_port", 587))

            if use_ssl:
                with smtplib.SMTP_SSL(config["smtp_server"], port, timeout=15) as server:
                    if config.get("smtp_user"):
                        server.login(config["smtp_user"], config["smtp_password"])
                    server.send_message(msg)
            else:
                with smtplib.SMTP(config["smtp_server"], port, timeout=15) as server:
                    server.ehlo()
                    if use_tls:
                        server.starttls()
                        server.ehlo()
                    if config.get("smtp_user"):
                        server.login(config["smtp_user"], config["smtp_password"])
                    server.send_message(msg)

            log.info(f"✓ Email envoyé à {recipient}")
        except Exception as e:
            log.error(f"❌ Erreur envoi email: {e}")


# ════════════════════════════════════════════════════════════════════════════
# EXEMPLE D'UTILISATION
# ════════════════════════════════════════════════════════════════════════════
def example_alert_from_snort():
    """Exemple d'alerte Snort reçue"""
    return {
        "source_ip": "192.168.1.100",
        "destination_ip": "192.168.1.200",
        "source_port": 45123,
        "destination_port": 80,
        "protocol": "TCP",
        "attack_type": "SQL Injection Attempt",
        "severity": "critical",
        "details": {
            "payload": "SELECT * FROM users WHERE id=1' OR '1'='1",
            "signature": "ET NETBIOS/RPC Exploit attempt",
            "confidence": 95,
        },
    }


if __name__ == "__main__":
    log.info("═" * 80)
    log.info("🛡️ Snort Alert Processor v1.0 - DÉMARRAGE")
    log.info("═" * 80)

    load_env()
    processor = SnortAlertProcessor()

    # Test avec une alerte d'exemple
    log.info("📝 Insertion d'une alerte de test...")
    test_alert = example_alert_from_snort()
    processor.insert_alert(test_alert)

    log.info("✓ Test complété")
    log.info(f"📁 Logs: {LOG_FILE}")
