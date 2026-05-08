from nornir import InitNornir
from nornir_netmiko.tasks import netmiko_send_config, netmiko_save_config
from nornir_utils.plugins.functions import print_result
import os


def build_nornir():
    """
    Initialise Nornir en lisant automatiquement hosts.yaml situé dans le même
    dossier que ce fichier. Aucune info SSH manuelle n'est nécessaire.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    hosts_file    = os.path.join(base_dir, "hosts.yaml")
    groups_file   = os.path.join(base_dir, "groups.yaml")
    defaults_file = os.path.join(base_dir, "defaults.yaml")

    inventory_options = {"host_file": hosts_file}
    if os.path.exists(groups_file):
        inventory_options["group_file"] = groups_file
    if os.path.exists(defaults_file):
        inventory_options["defaults_file"] = defaults_file

    return InitNornir(
        runner={"plugin": "threaded", "options": {"num_workers": 1}},
        inventory={"plugin": "YAMLInventory", "options": inventory_options},
    )


def build_commands(interface_name, mode, vlan_id, status,
                   port_security=False, max_mac=1, violation_mode="shutdown",
                   bpdu_guard=False, allowed_vlans=None, description=None,
                   static_mac=None):
    """
    Construit la liste de commandes IOS à envoyer pour configurer une interface.

    Paramètres :
        interface_name  : ex. "GigabitEthernet1/0/1"
        mode            : "access" ou "trunk"
        vlan_id         : int (ex. 17) — ignoré si mode=trunk
        status          : "UP" → no shutdown  /  "DOWN" → shutdown
        port_security   : bool — activer le port-security
        max_mac         : int  — max adresses MAC autorisées
        violation_mode  : "protect" | "restrict" | "shutdown"
        bpdu_guard      : bool — activer le BPDU Guard
        allowed_vlans   : str  — VLANs autorisés en trunk (ex. "10,20,30" ou "all")
        description     : str  — description de l'interface (optionnel)
    """
    cmds = [f"interface {interface_name}"]

    if description:
        cmds.append(f"description {description}")

    if mode == "trunk":
        cmds.append("switchport mode trunk")
        trunk_vlans = str(allowed_vlans).strip() if allowed_vlans else "all"
        if trunk_vlans.lower() == "all":
            cmds.append("switchport trunk allowed vlan all")
        else:
            cmds.append(f"switchport trunk allowed vlan {trunk_vlans}")
    else:
        cmds.append("switchport mode access")
        if vlan_id:
            cmds.append(f"switchport access vlan {vlan_id}")

    # Port Security (access uniquement)
    if port_security and mode == "access":
        cmds += [
            "switchport port-security",
            f"switchport port-security maximum {max_mac}",
            f"switchport port-security violation {violation_mode}",
        ]
        # MAC statique prioritaire sur sticky
        mac_clean = (static_mac or "").strip().replace("-", ".").replace(":", ".")
        if mac_clean:
            cmds.append(f"switchport port-security mac-address {mac_clean}")
        else:
            cmds.append("switchport port-security mac-address sticky")

    # BPDU Guard
    if bpdu_guard:
        cmds.append("spanning-tree bpduguard enable")
    else:
        cmds.append("no spanning-tree bpduguard enable")

    # Statut du port
    cmds.append("shutdown" if status == "DOWN" else "no shutdown")

    cmds.append("exit")
    return cmds


def run_deploy(interface_name, mode="access", vlan_id=1, status="UP",
               port_security=False, max_mac=1, violation_mode="shutdown",
               bpdu_guard=False, allowed_vlans=None, description=None,
               static_mac=None,
               switch_ip=None, switch_user=None, switch_password=None):
    """
    Déploie la configuration d'une interface sur le switch Cisco via SSH/Netmiko.

    Si switch_ip / switch_user / switch_password sont fournis (depuis la BDD),
    ils sont utilisés directement via Netmiko sans passer par hosts.yaml.
    Sinon, fallback sur hosts.yaml (compatibilité ascendante / test manuel).

    Retourne : {"success": bool, "message"/"error": str, "commands": list}
    """
    commands = build_commands(
        interface_name=interface_name,
        mode=mode,
        vlan_id=vlan_id,
        status=status,
        port_security=port_security,
        max_mac=max_mac,
        violation_mode=violation_mode,
        bpdu_guard=bpdu_guard,
        allowed_vlans=allowed_vlans,
        description=description,
        static_mac=static_mac,
    )

    print(f"\n{'='*55}")
    src = f"{switch_ip} (source : BDD switchs)" if switch_ip else "hosts.yaml"
    print(f"  🔌 Connexion SSH → {src}")
    print(f"{'='*55}")
    print(f"  Interface  : {interface_name}")
    print(f"  Mode       : {mode.upper()}")
    if mode == "access":
        print(f"  VLAN       : {vlan_id}")
    else:
        print(f"  VLANs trunk: {allowed_vlans or 'all'}")
    print(f"  Statut     : {'NO SHUTDOWN 🟢' if status == 'UP' else 'SHUTDOWN 🔴'}")
    print(f"  Port Sec   : {'✅ Activé' if port_security else '❌ Désactivé'}")
    if port_security and mode == "access":
        print(f"  Max MAC    : {max_mac}")
        print(f"  Violation  : {violation_mode.upper()}")
        if static_mac:
            print(f"  MAC statiq : {static_mac}")
        else:
            print(f"  MAC        : sticky")
    print(f"  BPDU Guard : {'✅ Activé' if bpdu_guard else '❌ Désactivé'}")
    print(f"{'='*55}")
    print(f"\n📋 Commandes à envoyer :")
    for c in commands:
        print(f"   {c}")
    print()

    # ── Chemin 1 : credentials fournis directement (depuis la table switchs) ──
    if switch_ip and switch_user and switch_password:
        try:
            from netmiko import ConnectHandler
            device = {
                "device_type": "cisco_ios",
                "host":        switch_ip,
                "username":    switch_user,
                "password":    switch_password,
                "port":        22,
            }
            net_connect = ConnectHandler(**device)
            output = net_connect.send_config_set(commands)
            net_connect.send_command("end")
            net_connect.send_command("write memory")
            net_connect.disconnect()
            print(f"🎉 Interface {interface_name} configurée et sauvegardée sur {switch_ip} !")
            return {
                "success":  True,
                "message":  f"Interface {interface_name} configurée et sauvegardée sur le switch {switch_ip}.",
                "commands": commands,
                "output":   output,
            }
        except Exception as e:
            print(f"❌ Erreur SSH sur {switch_ip} : {e}")
            return {"success": False, "error": str(e), "commands": commands}

    # ── Chemin 2 : fallback hosts.yaml ────────────────────────────────────────
    try:
        nr = build_nornir()

        if not nr.inventory.hosts:
            return {
                "success": False,
                "error": "Aucun host trouvé dans hosts.yaml. Vérifiez le fichier d'inventaire.",
                "commands": commands,
            }

        print(f"✅ Inventaire chargé. Switches : {list(nr.inventory.hosts.keys())}")
        print(f"📡 Envoi de la config interface {interface_name}...")

        result = nr.run(
            task=netmiko_send_config,
            config_commands=commands,
            name=f"Config {interface_name}",
        )

        if result.failed:
            errors = []
            for host, host_result in result.items():
                if host_result.failed:
                    exc = host_result[0].exception
                    print(f"❌ Erreur SSH sur {host} : {exc}")
                    errors.append(f"Erreur SSH sur {host} : {exc}")
            return {
                "success": False,
                "error": " | ".join(errors) or "Erreur inconnue.",
                "commands": commands,
            }

        print("\n--- RÉSULTAT SWITCH ---")
        print_result(result)
        print("-----------------------")

        print("💾 Sauvegarde (write memory)...")
        nr.run(task=netmiko_save_config)

        print(f"🎉 Interface {interface_name} configurée et sauvegardée !")
        return {
            "success": True,
            "message": f"Interface {interface_name} configurée et sauvegardée sur le switch.",
            "commands": commands,
        }

    except FileNotFoundError as e:
        msg = f"Fichier d'inventaire introuvable : {e}"
        print(f"❌ {msg}")
        return {"success": False, "error": msg, "commands": commands}

    except Exception as e:
        print(f"❌ Erreur critique : {e}")
        return {"success": False, "error": str(e), "commands": commands}


# ─── Test manuel ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Configure GigabitEthernet1/0/1 en access VLAN 17 avec port-security
    result = run_deploy(
        interface_name="GigabitEthernet1/0/1",
        mode="access",
        vlan_id=17,
        status="UP",
        port_security=True,
        max_mac=2,
        violation_mode="restrict",
        bpdu_guard=True,
        description="Access Port - Test",
    )
    print(result)