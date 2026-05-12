from flask import Blueprint, request, jsonify
from network.deploy_vlan import run_deploy as run_deploy_vlan
from network.interface_deploy import run_deploy as run_deploy_interface
import subprocess
import sys
import yaml, os
import logging
import shutil
import signal
from datetime import datetime

network_bp = Blueprint('network', __name__)
logger = logging.getLogger(__name__)

HOSTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network", "hosts.yaml")
RECUPERATION_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Snort", "Recuperation.py")
REMOTE_SNORT_USER = os.getenv("REMOTE_SNORT_USER", "Aya")
REMOTE_SNORT_HOST = os.getenv("REMOTE_SNORT_HOST", "10.10.10.31")
SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
DETECTION_PROCESS = None


def _load_hosts():
    with open(HOSTS_FILE, "r") as f:
        return yaml.safe_load(f) or {}


def _save_hosts(data):
    with open(HOSTS_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


@network_bp.route("/start-detection", methods=["POST"])
def start_detection():
    """Lance Snort et le script de recuperation sans bloquer Flask."""
    global DETECTION_PROCESS
    try:
        if DETECTION_PROCESS and DETECTION_PROCESS.poll() is None:
            return jsonify({
                "status": "ok",
                "message": "Detection deja lancee",
            })

        if not os.path.exists(RECUPERATION_SCRIPT):
            return jsonify({
                "status": "error",
                "message": f"Script introuvable: {RECUPERATION_SCRIPT}",
            }), 500

        if not shutil.which("ssh"):
            return jsonify({
                "status": "error",
                "message": "Commande ssh introuvable. Installez OpenSSH Client ou ajoutez ssh.exe au PATH.",
            }), 500

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        DETECTION_PROCESS = subprocess.Popen(
            [sys.executable, RECUPERATION_SCRIPT],
            cwd=os.path.dirname(RECUPERATION_SCRIPT),
            creationflags=creationflags,
        )

        return jsonify({
            "status": "ok",
            "message": "Détection lancée",
        })
    except Exception as e:
        logger.exception("Erreur lancement detection")
        return jsonify({
            "status": "error",
            "message": str(e),
        }), 500


@network_bp.route("/stop-detection", methods=["POST"])
def stop_detection():
    """Arrete Snort sans bloquer Flask."""
    global DETECTION_PROCESS
    try:
        if shutil.which("ssh"):
            remote_target = f"{REMOTE_SNORT_USER}@{REMOTE_SNORT_HOST}"
            subprocess.run(
                ["ssh", *SSH_OPTIONS, remote_target, "sudo -n pkill snort"],
                capture_output=True,
                text=True,
                timeout=30,
            )

        if DETECTION_PROCESS and DETECTION_PROCESS.poll() is None:
            if os.name == "nt":
                DETECTION_PROCESS.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                DETECTION_PROCESS.terminate()
            try:
                DETECTION_PROCESS.wait(timeout=8)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(DETECTION_PROCESS.pid), "/T", "/F"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                else:
                    DETECTION_PROCESS.kill()
        DETECTION_PROCESS = None

        return jsonify({
            "status": "ok",
            "message": "Détection arrêtée",
        })
    except Exception as e:
        logger.exception("Erreur arret detection")
        return jsonify({
            "status": "error",
            "message": str(e),
        }), 500


# ── Lire la config du switch depuis hosts.yaml ────────────────────────────────
@network_bp.route("/api/network/switch-config", methods=["GET"])
def get_switch_config():
    """Retourne les infos du switch stockées dans hosts.yaml."""
    try:
        hosts = _load_hosts()
        switches = []
        for host_key, host_val in hosts.items():
            conn = (host_val.get("connection_options") or {}).get("netmiko", {}).get("extras", {})
            switches.append({
                "host_key":  host_key,
                "hostname":  host_val.get("hostname", ""),
                "username":  host_val.get("username", ""),
                "password":  host_val.get("password", ""),
                "platform":  host_val.get("platform", "ios"),
                "port":      host_val.get("port", 22),
                "secret":    conn.get("secret", ""),
            })
        return jsonify({"success": True, "switches": switches})
    except FileNotFoundError:
        return jsonify({"success": False, "error": "hosts.yaml introuvable"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Mettre à jour la config du switch dans hosts.yaml ────────────────────────
@network_bp.route("/api/network/switch-config", methods=["POST"])
def update_switch_config():
    """
    Met à jour hosts.yaml avec les nouvelles infos SSH.
    Body attendu : { host_key, hostname, username, password, port, secret }
    """
    data = request.json or {}
    host_key = data.get("host_key", "switch_cible")
    hostname = data.get("hostname", "").strip()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    port     = int(data.get("port", 22))
    secret   = data.get("secret", "").strip()

    if not hostname or not username:
        return jsonify({"success": False, "error": "hostname et username sont requis"}), 400

    try:
        try:
            hosts = _load_hosts()
        except FileNotFoundError:
            hosts = {}

        if host_key not in hosts:
            hosts[host_key] = {"platform": "ios"}

        hosts[host_key]["hostname"] = hostname
        hosts[host_key]["username"] = username
        hosts[host_key]["password"] = password
        hosts[host_key]["port"]     = port

        if secret:
            hosts[host_key].setdefault("connection_options", {}) \
                           .setdefault("netmiko", {}) \
                           .setdefault("extras", {})["secret"] = secret

        _save_hosts(hosts)
        return jsonify({"success": True, "message": "hosts.yaml mis à jour avec succès."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Déploiement VLAN direct (sans BDD) ───────────────────────────────────────
@network_bp.route("/api/network/deploy-vlan/direct", methods=["POST"])
def api_deploy_vlan_direct():
    """Déploie un VLAN directement sur le switch (hosts.yaml, sans BDD)."""
    data      = request.json or {}
    vlan_id   = data.get("vlan_id") or data.get("id")
    vlan_name = data.get("vlan_name") or data.get("name") or data.get("nom")

    if not vlan_id or not vlan_name:
        return jsonify({"success": False, "error": "L'ID et le nom du VLAN sont requis."}), 400

    try:
        result = run_deploy_vlan(int(vlan_id), str(vlan_name))
        return jsonify(result), 200 if result.get("success") else 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Déploiement Interface sur le switch via SSH ───────────────────────────────
@network_bp.route("/api/network/deploy-interface", methods=["POST"])
def api_deploy_interface():
    """
    Déploie la configuration d'une interface sur le switch Cisco via SSH/Nornir.
    Les identifiants SSH sont lus automatiquement depuis network/hosts.yaml.

    Body JSON attendu :
        interface_name  (str)  ex. "GigabitEthernet1/0/1"
        mode            (str)  "access" | "trunk"
        vlan_id         (int)  VLAN ID (ignoré si mode=trunk)
        status          (str)  "UP" | "DOWN"
        port_security   (bool) activer le port-security
        max_mac         (int)  max adresses MAC
        violation_mode  (str)  "protect" | "restrict" | "shutdown"
        bpdu_guard      (bool) activer le BPDU Guard
        allowed_vlans   (str)  VLANs trunk autorisés ex. "10,20,30" ou "all"
        description     (str)  description du port (optionnel)
    """
    data = request.json or {}

    interface_name = data.get("interface_name", "").strip()
    if not interface_name:
        return jsonify({"success": False, "error": "interface_name est requis."}), 400

    mode          = str(data.get("mode", "access")).strip().lower()
    vlan_id_raw   = data.get("vlan_id")
    status        = str(data.get("status", "UP")).strip().upper()
    port_security = bool(data.get("port_security", False))
    max_mac       = int(data.get("max_mac", 1))
    violation     = str(data.get("violation_mode", "shutdown")).strip().lower()
    bpdu_guard    = bool(data.get("bpdu_guard", False))
    allowed_vlans = data.get("allowed_vlans") or None
    description   = data.get("description") or None
    static_mac    = (data.get("static_mac") or "").strip() or None
    remove_port_security = bool(data.get("remove_port_security", False))

    # Validation basique
    if mode not in ("access", "trunk"):
        return jsonify({"success": False, "error": "mode doit être 'access' ou 'trunk'."}), 400

    if status not in ("UP", "DOWN"):
        return jsonify({"success": False, "error": "status doit être 'UP' ou 'DOWN'."}), 400

    try:
        vlan_id = int(vlan_id_raw) if vlan_id_raw is not None else None
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "vlan_id doit être un entier."}), 400

    if mode == "access" and not vlan_id:
        return jsonify({"success": False, "error": "vlan_id est requis en mode access."}), 400

    try:
        # Si port-security est désactivé, on envoie d'abord les commandes "no" sur le switch
        if remove_port_security:
            try:
                from network.interface_deploy import build_nornir
                from nornir_netmiko.tasks import netmiko_send_config
                nr = build_nornir()
                if nr.inventory.hosts:
                    no_ps_commands = [
                        f"interface {interface_name}",
                        "no switchport port-security mac-address sticky",
                        "no switchport port-security maximum",
                        "no switchport port-security violation",
                        "no switchport port-security",
                        "exit",
                    ]
                    nr.run(task=netmiko_send_config, config_commands=no_ps_commands,
                           name=f"Remove port-security {interface_name}")
                    logger.info(f"[deploy-interface] Port-security supprimé sur {interface_name}")
            except Exception as ps_err:
                logger.warning(f"[deploy-interface] Avertissement suppression port-security: {ps_err}")

        result = run_deploy_interface(
            interface_name=interface_name,
            mode=mode,
            vlan_id=vlan_id,
            status=status,
            port_security=port_security,
            max_mac=max_mac,
            violation_mode=violation,
            bpdu_guard=bpdu_guard,
            allowed_vlans=allowed_vlans,
            description=description,
            static_mac=static_mac,
        )
        http_code = 200 if result.get("success") else 500
        return jsonify(result), http_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Suppression / Reset d'une interface sur le switch ────────────────────────
@network_bp.route("/api/network/remove-port-security", methods=["POST"])
def api_remove_port_security():
    """
    Supprime le port-security d'une interface Cisco via SSH.
    Envoie les commandes 'no switchport port-security ...' sur le switch.

    Body JSON attendu :
        interface_name  (str)  ex. "GigabitEthernet1/0/1"
    """
    data = request.json or {}
    interface_name = data.get("interface_name", "").strip()
    if not interface_name:
        return jsonify({"success": False, "error": "interface_name est requis."}), 400

    remove_commands = [
        f"interface {interface_name}",
        "no switchport port-security mac-address sticky",
        "no switchport port-security maximum",
        "no switchport port-security violation",
        "no switchport port-security",
        "exit",
    ]

    try:
        from network.interface_deploy import build_nornir
        from nornir_netmiko.tasks import netmiko_send_config, netmiko_save_config

        nr = build_nornir()
        if not nr.inventory.hosts:
            return jsonify({
                "success": False,
                "error": "Aucun host trouvé dans hosts.yaml.",
                "commands": remove_commands,
            }), 500

        result = nr.run(
            task=netmiko_send_config,
            config_commands=remove_commands,
            name=f"Remove port-security {interface_name}",
        )

        if result.failed:
            errors = []
            for host, host_result in result.items():
                if host_result.failed:
                    errors.append(f"Erreur SSH sur {host} : {host_result[0].exception}")
            return jsonify({
                "success": False,
                "error": " | ".join(errors) or "Erreur inconnue.",
                "commands": remove_commands,
            }), 500

        nr.run(task=netmiko_save_config)
        return jsonify({
            "success": True,
            "message": f"Port-security supprimé sur {interface_name}.",
            "commands": remove_commands,
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e), "commands": remove_commands}), 500


# ── Suppression / Reset d'une interface sur le switch ────────────────────────
@network_bp.route("/api/network/reset-interface", methods=["POST"])
def api_reset_interface():
    """
    Remet une interface à sa configuration par défaut sur le switch Cisco.
    Supprime : port-security, BPDU guard, description, remet en access VLAN 1, shutdown.

    Body JSON attendu :
        interface_name  (str)  ex. "GigabitEthernet1/0/1"
    """
    data = request.json or {}
    interface_name = data.get("interface_name", "").strip()
    if not interface_name:
        return jsonify({"success": False, "error": "interface_name est requis."}), 400

    reset_commands = [
        f"interface {interface_name}",
        "no description",
        "switchport mode access",
        "switchport access vlan 1",
        "no switchport port-security mac-address sticky",
        "no switchport port-security maximum",
        "no switchport port-security violation",
        "no switchport port-security",
        "no spanning-tree bpduguard enable",
        "shutdown",
        "exit",
    ]

    try:
        from network.interface_deploy import build_nornir
        from nornir_netmiko.tasks import netmiko_send_config, netmiko_save_config

        nr = build_nornir()
        if not nr.inventory.hosts:
            return jsonify({
                "success": False,
                "error": "Aucun host trouvé dans hosts.yaml.",
                "commands": reset_commands,
            }), 500

        result = nr.run(
            task=netmiko_send_config,
            config_commands=reset_commands,
            name=f"Reset {interface_name}",
        )

        if result.failed:
            errors = []
            for host, host_result in result.items():
                if host_result.failed:
                    errors.append(f"Erreur SSH sur {host} : {host_result[0].exception}")
            return jsonify({
                "success": False,
                "error": " | ".join(errors) or "Erreur inconnue.",
                "commands": reset_commands,
            }), 500

        nr.run(task=netmiko_save_config)
        return jsonify({
            "success": True,
            "message": f"Interface {interface_name} réinitialisée et sauvegardée sur le switch.",
            "commands": reset_commands,
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e), "commands": reset_commands}), 500

# ── Port Mirroring (SPAN) ────────────────────────────────────────────────────
@network_bp.route("/api/network/port-mirroring", methods=["POST"])
def api_port_mirroring():
    """
    Configure une session SPAN (port mirroring) sur le switch Cisco.

    Body JSON attendu :
        session_id             (int)      ex. 1
        source_vlan            (str|int)  ex. 10
        destination_interface  (str)      ex. "Gi1/0/19"
    """
    data = request.json or {}

    try:
        session_id = int(data.get("session_id", 1))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "session_id doit être un entier."}), 400

    source_vlan           = str(data.get("source_vlan", "")).strip()
    destination_interface = str(data.get("destination_interface", "")).strip()

    if not source_vlan:
        return jsonify({"success": False, "error": "source_vlan est requis."}), 400
    if not destination_interface:
        return jsonify({"success": False, "error": "destination_interface est requis."}), 400
    if not source_vlan.isdigit():
        return jsonify({"success": False, "error": "source_vlan doit être numérique."}), 400

    span_commands = [
        f"no monitor session {session_id}",
        f"monitor session {session_id} source vlan {source_vlan} both",
        f"monitor session {session_id} destination interface {destination_interface} ingress",
    ]

    try:
        from network.interface_deploy import build_nornir
        from nornir.core.task import Result, Task
        from nornir_netmiko.tasks import netmiko_save_config

        nr = build_nornir()
        if not nr.inventory.hosts:
            return jsonify({
                "success": False,
                "error": "Aucun host trouvé dans hosts.yaml.",
                "commands": span_commands,
            }), 500

        def port_mirroring_task(task: Task) -> Result:
            conn = task.host.get_connection("netmiko", task.nornir.config)
            output = conn.send_config_set(
                span_commands,
                read_timeout=30,
                cmd_verify=False,
            )
            verification = conn.send_command(f"show monitor session {session_id}")
            return Result(host=task.host, result={
                "output": output,
                "verification": verification,
            })

        result = nr.run(task=port_mirroring_task, name=f"Port Mirroring Session {session_id}")

        if result.failed:
            errors = []
            for host, host_result in result.items():
                if host_result.failed:
                    errors.append(f"Erreur SSH sur {host} : {host_result[0].exception}")
            return jsonify({
                "success": False,
                "error": " | ".join(errors) or "Erreur inconnue.",
                "commands": span_commands,
            }), 500

        nr.run(task=netmiko_save_config)

        outputs, verifications = [], []
        for host, host_result in result.items():
            payload = host_result[0].result or {}
            outputs.append(f"[{host}]\n{payload.get('output', '').strip()}".strip())
            verifications.append(f"[{host}]\n{payload.get('verification', '').strip()}".strip())

        return jsonify({
            "success": True,
            "message": f"Session SPAN {session_id} configurée : VLAN {source_vlan} → {destination_interface}.",
            "commands": span_commands,
            "output": "\n\n".join(outputs),
            "verification": "\n\n".join(verifications),
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "commands": span_commands,
        }), 500


# ── Suppression session SPAN ─────────────────────────────────────────────────
@network_bp.route("/api/network/port-mirroring/delete", methods=["POST"])
def api_delete_port_mirroring():
    """
    Supprime une session SPAN (port mirroring) sur le switch Cisco.

    Body JSON attendu :
        session_id  (int)  ex. 1
    """
    data = request.json or {}

    try:
        session_id = int(data.get("session_id", 1))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "session_id doit être un entier."}), 400

    delete_commands = [f"no monitor session {session_id}"]

    try:
        from network.interface_deploy import build_nornir
        from nornir.core.task import Result, Task
        from nornir_netmiko.tasks import netmiko_save_config

        nr = build_nornir()
        if not nr.inventory.hosts:
            return jsonify({
                "success": False,
                "error": "Aucun host trouvé dans hosts.yaml.",
                "commands": delete_commands,
            }), 500

        def delete_mirroring_task(task: Task) -> Result:
            conn = task.host.get_connection("netmiko", task.nornir.config)
            output = conn.send_config_set(delete_commands, read_timeout=20, cmd_verify=False)
            verification = conn.send_command(f"show monitor session {session_id}")
            return Result(host=task.host, result={
                "output": output,
                "verification": verification,
            })

        result = nr.run(task=delete_mirroring_task, name=f"Delete SPAN Session {session_id}")

        if result.failed:
            errors = []
            for host, host_result in result.items():
                if host_result.failed:
                    errors.append(f"Erreur SSH sur {host} : {host_result[0].exception}")
            return jsonify({
                "success": False,
                "error": " | ".join(errors) or "Erreur inconnue.",
                "commands": delete_commands,
            }), 500

        nr.run(task=netmiko_save_config)

        verifications = []
        for host, host_result in result.items():
            payload = host_result[0].result or {}
            verifications.append(f"[{host}]\n{payload.get('verification', '').strip()}".strip())

        return jsonify({
            "success": True,
            "message": f"Session SPAN {session_id} supprimée.",
            "commands": delete_commands,
            "verification": "\n\n".join(verifications),
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "commands": delete_commands,
        }), 500


# ── TFTP Backup : copy running-config ou startup-config → serveur TFTP ──────
@network_bp.route("/api/network/tftp-backup", methods=["POST"])
def api_tftp_backup():
    """
    Sauvegarde la running-config ou startup-config du switch vers un serveur TFTP.

    Body JSON attendu :
        tftp_server  (str)  IP du serveur TFTP  ex. "192.168.1.100"
        filename     (str)  Nom du fichier       ex. "running-config.cfg"
        config_type  (str)  "running" | "startup"  (défaut: "running")
    """
    data        = request.json or {}
    tftp_server = data.get("tftp_server", "").strip()
    filename    = data.get("filename",    "running-config.cfg").strip()
    config_type = data.get("config_type", "running").strip().lower()

    if not tftp_server:
        logger.warning(f"[TFTP-BACKUP] Erreur: tftp_server vide")
        return jsonify({"success": False, "error": "tftp_server est requis."}), 400

    if config_type not in ("running", "startup"):
        logger.warning(f"[TFTP-BACKUP] Erreur: config_type invalide: {config_type}")
        return jsonify({"success": False, "error": "config_type doit être 'running' ou 'startup'."}), 400

    logger.info(f"[TFTP-BACKUP] Début - Serveur: {tftp_server}, Config: {config_type}, Fichier: {filename}")

    try:
        from network.interface_deploy import build_nornir
        from nornir.core.task import Task, Result

        nr = build_nornir()
        if not nr.inventory.hosts:
            logger.error(f"[TFTP-BACKUP] Aucun host trouvé dans hosts.yaml")
            return jsonify({"success": False, "error": "Aucun host dans hosts.yaml."}), 500

        all_output = []

        def tftp_backup_task(task: Task) -> Result:
            try:
                conn = task.host.get_connection("netmiko", task.nornir.config)
                
                # Choisir la source selon le type de config
                source_config = "running-config" if config_type == "running" else "startup-config"
                
                # Commande TFTP avec URL complète
                cmd = f"copy {source_config} tftp://{tftp_server}/{filename}"
                logger.debug(f"[TFTP-BACKUP][{task.host.name}] Commande: {cmd}")
                
                # Envoyer la commande avec timeout robuste
                output = conn.send_command_timing(
                    cmd, 
                    delay_factor=2.0,
                    max_loops=200,  # Augmenté pour les configs volumineuses
                    strip_prompt=False,
                    strip_command=False
                )
                
                # Gérer les prompts Cisco courants
                # - "Destination filename [xxxx.cfg]?" → confirmer le nom
                # - "... bytes copied in ..." → succès
                # - "% Error" → erreur d'auth ou réseau
                
                if "Destination filename" in output:
                    logger.debug(f"[TFTP-BACKUP][{task.host.name}] Prompt détecté: Destination filename")
                    output += conn.send_command_timing(filename, delay_factor=2.0, max_loops=150)
                
                if "?" in output and "Destination" not in output:
                    logger.debug(f"[TFTP-BACKUP][{task.host.name}] Confirmant avec Entrée")
                    output += conn.send_command_timing("", delay_factor=2.0, max_loops=50)
                
                all_output.append(output)
                
                # Détection d'erreurs
                if "Error" in output or "error" in output.lower() or "timeout" in output.lower():
                    logger.error(f"[TFTP-BACKUP][{task.host.name}] Erreur détectée dans la sortie")
                    raise Exception(f"Erreur TFTP sur {task.host.name}: {output.strip()[-200:]}")
                
                if "bytes copied" not in output.lower() and "percent" not in output.lower():
                    logger.warning(f"[TFTP-BACKUP][{task.host.name}] Pas de confirmation de succès")
                    raise Exception(f"Confirmation de sauvegarde manquante sur {task.host.name}")
                
                logger.info(f"[TFTP-BACKUP][{task.host.name}] Sauvegarde réussie")
                return Result(host=task.host, result=output)
                
            except Exception as e:
                logger.error(f"[TFTP-BACKUP][{task.host.name}] Exception: {str(e)}")
                raise

        result = nr.run(task=tftp_backup_task, name=f"TFTP Backup {config_type}-config")

        if result.failed:
            errors = []
            for host_name, host_result in result.items():
                if host_result.failed:
                    errors.append(f"Erreur SSH sur {host_name}: {host_result[0].exception}")
            error_msg = " | ".join(errors) or "Erreur inconnue"
            logger.error(f"[TFTP-BACKUP] Échec: {error_msg}")
            return jsonify({
                "success": False,
                "error": error_msg,
                "output": "\n".join(all_output)
            }), 500

        output_text = "\n".join(all_output)
        logger.info(f"[TFTP-BACKUP] Succès - Sauvegardée → tftp://{tftp_server}/{filename}")
        
        return jsonify({
            "success": True,
            "message": f"{config_type}-config sauvegardée → tftp://{tftp_server}/{filename}",
            "output": output_text,
            "config_type": config_type,
            "timestamp": datetime.now().isoformat()
        }), 200

    except Exception as e:
        logger.exception(f"[TFTP-BACKUP] Exception globale")
        return jsonify({"success": False, "error": f"Erreur interne: {str(e)}"}), 500


# ── TFTP Restore : copy TFTP → running-config ou startup-config ──────────────
@network_bp.route("/api/network/tftp-restore", methods=["POST"])
def api_tftp_restore():
    """
    Restaure la configuration du switch depuis un serveur TFTP.

    Body JSON attendu :
        tftp_server  (str)  IP du serveur TFTP  ex. "192.168.1.100"
        filename     (str)  Nom du fichier       ex. "running-config.cfg"
        config_type  (str)  "running" | "startup"  (défaut: "running")
    """
    data        = request.json or {}
    tftp_server = data.get("tftp_server", "").strip()
    filename    = data.get("filename",    "running-config.cfg").strip()
    config_type = data.get("config_type", "running").strip().lower()

    if not tftp_server:
        logger.warning(f"[TFTP-RESTORE] Erreur: tftp_server vide")
        return jsonify({"success": False, "error": "tftp_server est requis."}), 400

    if config_type not in ("running", "startup"):
        logger.warning(f"[TFTP-RESTORE] Erreur: config_type invalide: {config_type}")
        return jsonify({"success": False, "error": "config_type doit être 'running' ou 'startup'."}), 400

    logger.info(f"[TFTP-RESTORE] Début - Serveur: {tftp_server}, Config: {config_type}, Fichier: {filename}")

    try:
        from network.interface_deploy import build_nornir
        from nornir.core.task import Task, Result

        nr = build_nornir()
        if not nr.inventory.hosts:
            logger.error(f"[TFTP-RESTORE] Aucun host trouvé dans hosts.yaml")
            return jsonify({"success": False, "error": "Aucun host dans hosts.yaml."}), 500

        all_output = []

        def tftp_restore_task(task: Task) -> Result:
            try:
                conn = task.host.get_connection("netmiko", task.nornir.config)
                
                # Choisir la destination selon le type de config
                dest_config = "running-config" if config_type == "running" else "startup-config"
                
                # Commande TFTP avec URL complète
                cmd = f"copy tftp://{tftp_server}/{filename} {dest_config}"
                logger.debug(f"[TFTP-RESTORE][{task.host.name}] Commande: {cmd}")
                
                # Envoyer avec timeout robuste
                output = conn.send_command_timing(
                    cmd,
                    delay_factor=2.0,
                    max_loops=200,
                    strip_prompt=False,
                    strip_command=False
                )
                
                # Gérer les prompts Cisco
                if "Destination filename" in output:
                    logger.debug(f"[TFTP-RESTORE][{task.host.name}] Prompt détecté: Destination filename")
                    output += conn.send_command_timing("", delay_factor=2.0, max_loops=150)
                
                if "File exists" in output or "Overwrite" in output:
                    logger.debug(f"[TFTP-RESTORE][{task.host.name}] Confirming overwrite")
                    output += conn.send_command_timing("yes", delay_factor=2.0, max_loops=150)
                elif "?" in output and "bytes" not in output:
                    logger.debug(f"[TFTP-RESTORE][{task.host.name}] Confirmant avec Entrée")
                    output += conn.send_command_timing("", delay_factor=2.0, max_loops=50)
                
                all_output.append(output)
                
                # Détection d'erreurs
                if "Error" in output or "error" in output.lower() or "timeout" in output.lower():
                    logger.error(f"[TFTP-RESTORE][{task.host.name}] Erreur détectée")
                    raise Exception(f"Erreur TFTP sur {task.host.name}: {output.strip()[-200:]}")
                
                if "bytes copied" not in output.lower() and "percent" not in output.lower():
                    logger.warning(f"[TFTP-RESTORE][{task.host.name}] Pas de confirmation de succès")
                    raise Exception(f"Confirmation de restauration manquante sur {task.host.name}")
                
                logger.info(f"[TFTP-RESTORE][{task.host.name}] Restauration réussie")
                return Result(host=task.host, result=output)
                
            except Exception as e:
                logger.error(f"[TFTP-RESTORE][{task.host.name}] Exception: {str(e)}")
                raise

        result = nr.run(task=tftp_restore_task, name=f"TFTP Restore {config_type}-config")

        if result.failed:
            errors = []
            for host_name, host_result in result.items():
                if host_result.failed:
                    errors.append(f"Erreur SSH sur {host_name}: {host_result[0].exception}")
            error_msg = " | ".join(errors) or "Erreur inconnue"
            logger.error(f"[TFTP-RESTORE] Échec: {error_msg}")
            return jsonify({
                "success": False,
                "error": error_msg,
                "output": "\n".join(all_output)
            }), 500

        output_text = "\n".join(all_output)
        logger.info(f"[TFTP-RESTORE] Succès - Restaurée depuis tftp://{tftp_server}/{filename}")

        # Sauvegarder la configuration en NVRAM si running-config
        if config_type == "running":
            logger.info(f"[TFTP-RESTORE] Sauvegarde en NVRAM (write memory)...")
            from nornir_netmiko.tasks import netmiko_save_config
            save_result = nr.run(task=netmiko_save_config)
            if save_result.failed:
                logger.warning(f"[TFTP-RESTORE] Avertissement: write memory a échoué")
        
        return jsonify({
            "success": True,
            "message": f"{config_type}-config restaurée depuis tftp://{tftp_server}/{filename}" + 
                      (" et sauvegardée en NVRAM" if config_type == "running" else ""),
            "output": output_text,
            "config_type": config_type,
            "timestamp": datetime.now().isoformat()
        }), 200

    except Exception as e:
        logger.exception(f"[TFTP-RESTORE] Exception globale")
        return jsonify({"success": False, "error": f"Erreur interne: {str(e)}"}), 500
