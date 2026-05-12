# snort_manager_windows.py
#!/usr/bin/env python3
import subprocess
import time
import threading
import re
import os
import sys
import json
import urllib.error
import urllib.request
from datetime import datetime
import psutil  # pip install psutil

REMOTE_SNORT_USER = "Aya"
REMOTE_SNORT_HOST = "10.10.10.31"
REMOTE_SNORT_CONFIG = "/etc/snort/snort.conf"
REMOTE_SNORT_LOG_DIR = "/var/log/snort"
REMOTE_SNORT_ALERT_FILE = "/var/log/snort/alert"
ALERTS_API_URL = os.getenv("ALERTS_API_URL", "http://127.0.0.1:5000/api/alerts")
SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
SAFE_INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


def print_sudo_setup_commands():
    """Affiche les commandes Ubuntu pour autoriser Snort sans mot de passe."""
    print(f"""
# A executer une seule fois sur Ubuntu ({REMOTE_SNORT_HOST}) avec un compte sudo.
# Cela ne desactive pas sudo globalement: seul l'utilisateur {REMOTE_SNORT_USER}
# pourra lancer les commandes necessaires sans demande de mot de passe.

SNORT_BIN=$(command -v snort)
PKILL_BIN=$(command -v pkill)
IP_BIN=$(command -v ip)
TAIL_BIN=$(command -v tail)

echo "{REMOTE_SNORT_USER} ALL=(ALL) NOPASSWD: $SNORT_BIN, $PKILL_BIN, $IP_BIN, $TAIL_BIN" | sudo tee /etc/sudoers.d/snort-web
sudo chmod 440 /etc/sudoers.d/snort-web
sudo visudo -cf /etc/sudoers.d/snort-web
""".strip())


class SnortManager:
    def __init__(self, interface="enp0s8", log_dir="C:\\Snort\\log"):
        """
        Args:
            interface: Nom de l'interface reseau distante (ex: "enp0s8")
            log_dir: Dossier local conserve pour compatibilite
        """
        self.interface = interface
        self.log_dir = log_dir
        self.alert_file = os.path.join(log_dir, "alert")  # Format fast alert
        self.snort_process = None
        self.alert_tail_process = None
        self.snort_running = False
        self.alert_count = 0
        self.api_insert_count = 0
        self.packet_count = 0
        
        # Créer le dossier des logs
        os.makedirs(log_dir, exist_ok=True)
        
        # Nettoyer l'ancien fichier d'alertes
        if os.path.exists(self.alert_file):
            try:
                os.remove(self.alert_file)
            except:
                pass
        
        self.init_database()
    
    def init_database(self):
        """Initialise la cible API utilisee pour enregistrer les alertes."""
        print(f"API alertes: {ALERTS_API_URL}")
    
    def create_tables_if_not_exists(self):
        """La creation des tables est geree cote API/base de donnees."""
        return None
    
    def convert_timestamp(self, timestamp_str):
        """Convertit le timestamp Snort (MM/DD-HH:MM:SS) en format PostgreSQL"""
        try:
            # Format Snort: "04/29-10:30:45.123456"
            date_part, time_part = timestamp_str.split('-')
            month, day = date_part.split('/')
            year = datetime.now().year
            # Prendre seulement les 8 premiers caractères pour HH:MM:SS
            time_clean = time_part[:8] if len(time_part) >= 8 else time_part
            return f"{year}-{month}-{day} {time_clean}"
        except:
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def convert_severity(self, severity_value):
        """Convertit le niveau de priorité Snort en texte"""
        if severity_value == 0 or severity_value == 1:
            return 'élevée'
        elif severity_value == 2:
            return 'moyenne'
        elif severity_value == 3:
            return 'basse'
        return 'inconnue'
    
    def parse_alert(self, header_line, ip_line):
        """Parse une alerte Snort format fast"""
        timestamp = ""
        ts_match = re.search(r'(\d{2}/\d{2}-\d{2}:\d{2}:\d{2}\.\d+)', ip_line)
        if ts_match:
            timestamp = ts_match.group(1)
        else:
            timestamp = datetime.now().strftime("%m/%d-%H:%M:%S")
        
        sid = ""
        sid_match = re.search(r'\[(\d+:\d+:\d+)\]', header_line)
        if sid_match:
            sid = sid_match.group(1)
        
        msg = ""
        msg_match = re.search(r'\[\*\*\] \[[0-9:]+\] (.*) \[\*\*\]', header_line)
        if msg_match:
            msg = msg_match.group(1).strip()
        
        priority = 0
        prio_match = re.search(r'Priority: (\d+)', header_line)
        if prio_match:
            priority = int(prio_match.group(1))
        
        proto = ""
        proto_match = re.search(r'\{([^}]+)\}', ip_line)
        if proto_match:
            proto = proto_match.group(1)
        
        # Extraction IP:Port (format: 10.10.10.1:12345 -> 10.10.10.2:80)
        ip_ports = re.findall(r'(\d+\.\d+\.\d+\.\d+):(\d+)', ip_line)
        
        src_ip = None
        src_port = None
        dst_ip = None
        dst_port = None
        
        if len(ip_ports) >= 1:
            src_ip = ip_ports[0][0]
            src_port = int(ip_ports[0][1]) if ip_ports[0][1].isdigit() else None
        if len(ip_ports) >= 2:
            dst_ip = ip_ports[1][0]
            dst_port = int(ip_ports[1][1]) if ip_ports[1][1].isdigit() else None
        
        return {
            'timestamp_raw': timestamp,
            'timestamp': self.convert_timestamp(timestamp),
            'sid': sid,
            'src_ip': src_ip,
            'dst_ip': dst_ip,
            'attack_type': msg,
            'severity': priority,
            'protocol': proto,
            'src_port': src_port,
            'dst_port': dst_port,
            'detection_engine': sid.split(':')[0] if sid else 'Snort'
        }
    
    def send_alert_to_api(self, alert):
        """Envoie l'alerte a l'API alertes; l'API se charge de la BDD."""
        try:
            severity_text = self.convert_severity(alert['severity'])
            
            attack_type = alert['attack_type']
            if attack_type and len(attack_type) > 200:
                attack_type = attack_type[:200]
            
            details = alert['attack_type']
            if details and len(details) > 500:
                details = details[:500]
            
            payload = {
                "timestamp": alert['timestamp'],
                "source_ip": alert['src_ip'],
                "destination_ip": alert['dst_ip'],
                "attack_type": attack_type,
                "severity": severity_text,
                "detection_engine": alert['detection_engine'],
                "details": details,
                "protocol": alert['protocol'],
                "source_port": alert['src_port'],
                "destination_port": alert['dst_port'],
            }
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                ALERTS_API_URL,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status >= 400:
                    print(f"   Erreur API alertes: HTTP {response.status}")
                    return False

            self.api_insert_count += 1
            return True
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            print(f"   Erreur API alertes: HTTP {e.code} {body}")
            return False
        except urllib.error.URLError as e:
            print(f"   API alertes indisponible: {e.reason}")
            return False
        except Exception as e:
            print(f"   Erreur envoi alerte API: {e}")
            return False
    
    def start_snort(self):
        """Demarre Snort a distance via SSH sur le serveur Linux"""
        try:
            # Commande fixe: le backend lance Snort sur le serveur Linux via SSH.
            if not SAFE_INTERFACE_PATTERN.match(self.interface):
                print(f"Interface invalide: {self.interface}")
                return False

            remote_target = f"{REMOTE_SNORT_USER}@{REMOTE_SNORT_HOST}"
            remote_cmd = (
                f"sudo -n pkill snort || true; "
                f"sudo -n ip link set {self.interface} promisc on; "
                f"sudo -n snort -D -i {self.interface} -A fast "
                f"-l {REMOTE_SNORT_LOG_DIR} -c {REMOTE_SNORT_CONFIG} -k none"
            )
            cmd = ["ssh", *SSH_OPTIONS, remote_target, remote_cmd]
            
            print(f"\n{'=' * 80}")
            print("SNORT - SURVEILLANCE RESEAU (serveur Linux distant)")
            print(f"{'=' * 80}")
            print(f"Serveur: {remote_target}")
            print(f"Interface distante: {self.interface}")
            print(f"Alertes distantes: {REMOTE_SNORT_ALERT_FILE}")
            print(f"API alertes: {ALERTS_API_URL}")
            print(f"{'=' * 80}\n")
            
            # La commande Snort distante est lancee en daemon avec -D.
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"Erreur SSH/Snort: {result.stderr.strip()}")
                print("Configurez une cle SSH et sudo sans mot de passe pour cette commande.")
                print("Aide: python Recuperation.py --show-sudo-setup")
                return False

            self.snort_process = None
            self.snort_running = True

            thread = threading.Thread(target=self._tail_alerts, daemon=True)
            thread.start()
            
            print("Detection active")
            
            return True
        except Exception as e:
            print(f"Erreur demarrage Snort: {e}")
            return False
    
    def _update_packet_stats_windows(self):
        """Met à jour le compteur de paquets sur Windows via psutil"""
        last_bytes_sent = {}
        last_bytes_recv = {}
        
        while self.snort_running:
            try:
                # Obtenir les stats réseau via psutil
                net_stats = psutil.net_io_counters(pernic=True)
                
                if self.interface in net_stats:
                    current_recv = net_stats[self.interface].bytes_recv
                    current_sent = net_stats[self.interface].bytes_sent
                    
                    # Calculer la différence approximative en paquets
                    # (basé sur taille moyenne de paquet estimée à 1500 bytes)
                    if self.interface in last_bytes_recv:
                        diff_bytes = current_recv - last_bytes_recv[self.interface]
                        estimated_packets = diff_bytes // 1500  # Approximation
                        if estimated_packets > 0:
                            self.packet_count += estimated_packets
                    
                    last_bytes_recv[self.interface] = current_recv
                    last_bytes_sent[self.interface] = current_sent
                
            except Exception as e:
                pass
            
            time.sleep(5)
    
    def _tail_alerts(self):
        """Surveille le fichier d'alertes en temps réel"""
        time.sleep(2)

        remote_target = f"{REMOTE_SNORT_USER}@{REMOTE_SNORT_HOST}"
        cmd = [
            "ssh",
            *SSH_OPTIONS,
            remote_target,
            f"sudo -n tail -n 0 -F {REMOTE_SNORT_ALERT_FILE}"
        ]

        try:
            self.alert_tail_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            while self.snort_running and self.alert_tail_process.poll() is None:
                line = self.alert_tail_process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                line = line.strip()
                if not line or "[**]" not in line:
                    continue

                self.alert_count += 1
                alert = self.parse_alert(line, line)
                severity_text = self.convert_severity(alert['severity'])

                print(f"\nALERTE #{self.alert_count}: {alert['attack_type']} [{severity_text}]")
                print(f"   {alert['src_ip']}:{alert['src_port']} -> {alert['dst_ip']}:{alert['dst_port']}")

                self.send_alert_to_api(alert)

            if self.snort_running and self.alert_tail_process.returncode:
                error = self.alert_tail_process.stderr.read().strip()
                print(f"Erreur lecture alertes distantes: {error}")
        except Exception as e:
            print(f"Erreur lecture alertes distantes: {e}")

        return
        
        while self.snort_running and self.snort_process and self.snort_process.poll() is None:
            if os.path.exists(self.alert_file):
                try:
                    with open(self.alert_file, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(0, os.SEEK_END)
                        while self.snort_running:
                            line = f.readline()
                            if not line:
                                time.sleep(0.1)
                                continue
                            
                            line = line.strip()
                            if not line:
                                continue
                            
                            if "[**]" in line:
                                header_line = line
                                next_line = f.readline().strip()
                                if next_line:
                                    self.alert_count += 1
                                    alert = self.parse_alert(header_line, next_line)
                                    severity_text = self.convert_severity(alert['severity'])
                                    
                                    # Affichage coloré dans la console
                                    print(f"\n\033[91m🚨 ALERTE #{self.alert_count}: {alert['attack_type']} [{severity_text}]\033[0m")
                                    print(f"   📍 {alert['src_ip']}:{alert['src_port']} -> {alert['dst_ip']}:{alert['dst_port']}")
                                    
                                    # Sauvegarde en BDD
                                    self.send_alert_to_api(alert)
                except Exception as e:
                    print(f"⚠️ Erreur lecture alertes: {e}")
            else:
                time.sleep(1)
    
    def stop_snort(self):
        """Arrête Snort proprement"""
        try:
            remote_target = f"{REMOTE_SNORT_USER}@{REMOTE_SNORT_HOST}"
            subprocess.run(
                ["ssh", *SSH_OPTIONS, remote_target, "sudo -n pkill snort"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if self.alert_tail_process:
                self.alert_tail_process.terminate()
                try:
                    self.alert_tail_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.alert_tail_process.kill()

            if self.snort_process:
                self.snort_process.terminate()
                try:
                    self.snort_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.snort_process.kill()
        except:
            pass
        
        self.snort_running = False
        self.snort_process = None
        print(f"\n🛑 Snort arrêté")
        print(f"📊 Statistiques finales:")
        print(f"   - Alertes détectées: {self.alert_count}")
        print(f"   - Alertes envoyees a l'API: {self.api_insert_count}")
        print(f"   - Paquets estimés: {self.packet_count}")
    
    def is_running(self):
        return self.snort_running
    
    def get_packet_count(self):
        return self.packet_count
    
    def get_alert_count(self):
        return self.alert_count


# Gestionnaire global
_snort_manager = None


def start_snort(interface="enp0s8"):
    """Démarre Snort (fonction externe)"""
    global _snort_manager
    if _snort_manager is None:
        _snort_manager = SnortManager(interface=interface)
    return _snort_manager.start_snort()


def stop_snort():
    """Arrête Snort (fonction externe)"""
    global _snort_manager
    if _snort_manager:
        _snort_manager.stop_snort()
        _snort_manager = None


def get_packet_count():
    """Retourne le nombre de paquets (fonction externe)"""
    global _snort_manager
    if _snort_manager:
        return _snort_manager.get_packet_count()
    return 0


def get_alert_count():
    """Retourne le nombre d'alertes (fonction externe)"""
    global _snort_manager
    if _snort_manager:
        return _snort_manager.get_alert_count()
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Snort Manager SSH")
    parser.add_argument("--interface", default="enp0s8", help="Nom de l'interface reseau distante")
    parser.add_argument("--log-dir", default="C:\\Snort\\log", help="Dossier des logs")
    parser.add_argument("--show-sudo-setup", action="store_true", help="Afficher les commandes sudoers a executer sur Ubuntu")
    
    args = parser.parse_args()

    if args.show_sudo_setup:
        print_sudo_setup_commands()
        sys.exit(0)
    
    manager = SnortManager(interface=args.interface, log_dir=args.log_dir)
    try:
        manager.start_snort()
        print("Snort en cours d'exécution. Appuyez sur Ctrl+C pour arrêter.")
        while manager.is_running():
            time.sleep(1)
            # Afficher statut périodique
            if manager.alert_count > 0:
                print(f"\r📊 Alertes: {manager.alert_count} | API: {manager.api_insert_count}", end="")
    except KeyboardInterrupt:
        print("\n\nArrêt demandé...")
        manager.stop_snort()
