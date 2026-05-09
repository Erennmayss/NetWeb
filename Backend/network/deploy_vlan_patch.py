# ─────────────────────────────────────────────────────────────────────────────
# AJOUTEZ cette fonction dans votre fichier network/deploy_vlan.py
# (à côté de votre fonction run_deploy existante)
# ─────────────────────────────────────────────────────────────────────────────

def run_delete(id_vlan: int) -> dict:
    """
    Supprime un VLAN du switch via SSH.
    Lit les credentials depuis hosts.yaml (même logique que run_deploy).

    Commandes envoyées :
        conf t
        no vlan <id>
        no interface vlan <id>
        end
        write memory
    """
    # ── Charger hosts.yaml ────────────────────────────────────────────────────
    import os, yaml
    from netmiko import ConnectHandler

    base_dir = os.path.dirname(os.path.abspath(__file__))
    hosts_path = os.path.join(base_dir, "hosts.yaml")
    if not os.path.exists(hosts_path):
        return {"success": False, "error": f"hosts.yaml introuvable : {hosts_path}"}

    with open(hosts_path, "r") as f:
        hosts_data = yaml.safe_load(f)

    # Adapter selon votre format hosts.yaml (liste ou dict)
    if isinstance(hosts_data, list):
        host_cfg = hosts_data[0]
    elif isinstance(hosts_data, dict):
        first_key = next(iter(hosts_data))
        host_cfg = hosts_data[first_key] if isinstance(hosts_data[first_key], dict) else hosts_data
    else:
        return {"success": False, "error": "Format hosts.yaml invalide"}

    device = {
        "device_type": host_cfg.get("device_type", "cisco_ios"),
        "host":        host_cfg.get("hostname") or host_cfg.get("host"),
        "username":    host_cfg.get("username"),
        "password":    host_cfg.get("password"),
        "secret":      host_cfg.get("secret", ""),
        "port":        int(host_cfg.get("port", 22)),
    }

    if not device["host"] or not device["username"]:
        return {"success": False, "error": "Credentials SSH manquants dans hosts.yaml"}

    # ── Commandes de suppression ───────────────────────────────────────────────
    commands = [
        f"no vlan {id_vlan}",
        f"no interface vlan {id_vlan}",
    ]

    try:
        net_connect = ConnectHandler(**device)
        if device["secret"]:
            net_connect.enable()

        output = net_connect.send_config_set(commands)
        net_connect.send_command("end")
        net_connect.send_command("write memory")
        net_connect.disconnect()

        return {
            "success":  True,
            "message":  f"VLAN {id_vlan} supprimé du switch.",
            "commands": ["conf t"] + commands + ["end", "write memory"],
            "output":   output,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
