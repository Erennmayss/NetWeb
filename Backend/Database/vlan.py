from flask import Blueprint, jsonify, request
from Database.db import get_db_connection
import ipaddress
import psycopg2.extras

vlan_bp = Blueprint("vlan", __name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_vlan_columns(conn):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'vlan'
        """)
        return {row[0] for row in cur.fetchall()}
    finally:
        cur.close()


def derive_network_from_gateway(gateway):
    if not gateway:
        return ""
    try:
        return str(ipaddress.ip_network(f"{gateway}/24", strict=False))
    except ValueError:
        return ""


def build_vlan_response(row):
    gateway = row.get("gateway") or ""
    return {
        "id_vlan":    row.get("id_vlan"),
        "id":         row.get("id_vlan"),
        "nom":        row.get("nom"),
        "name":       row.get("nom"),
        "reseau":     row.get("reseau") or "",
        "gateway":    gateway,
        "vlanIp":     gateway or "--",
        "type":       row.get("type") or "Data",
        "ports":      row.get("ports") or "",
        "status":     row.get("status") or "Active",
        "switchName": row.get("switch_name") or "",
        "switchIp":   row.get("switch_ip") or "",
        "devices":    0,
    }


def normalize_vlan_payload(data, forced_vlan_id=None):
    if not isinstance(data, dict):
        raise ValueError("Le corps JSON est invalide")

    raw_id = forced_vlan_id if forced_vlan_id is not None else data.get("id_vlan", data.get("id", data.get("vlan_id")))
    try:
        id_vlan = int(raw_id)
    except (TypeError, ValueError):
        raise ValueError("id_vlan doit être un entier")

    gateway = str(data.get("gateway", data.get("vlanIp", data.get("vlan_ip", "")))).strip()
    reseau  = str(data.get("reseau", "")).strip()
    if not reseau and gateway:
        reseau = derive_network_from_gateway(gateway)

    payload = {
        "id_vlan":     id_vlan,
        "nom":         str(data.get("nom", data.get("name", data.get("vlan_name", "")))).strip(),
        "reseau":      reseau,
        "gateway":     gateway,
        "type":        str(data.get("type", "Data")).strip() or "Data",
        "ports":       str(data.get("ports", "")).strip(),
        "status":      str(data.get("status", "Active")).strip() or "Active",
        "switch_name": str(data.get("switchName", data.get("switch_name", ""))).strip(),
        "switch_ip":   str(data.get("switchIp",   data.get("switch_ip",   ""))).strip(),
    }

    if not payload["nom"]:
        raise ValueError("Le nom du VLAN est requis")

    if payload["gateway"]:
        try:
            ipaddress.ip_address(payload["gateway"])
        except ValueError:
            raise ValueError("gateway doit être une adresse IP valide")

    if payload["reseau"]:
        try:
            ipaddress.ip_network(payload["reseau"], strict=False)
        except ValueError:
            raise ValueError("reseau doit être au format CIDR, ex: 192.168.10.0/24")

    return payload


def get_returning_fields(columns):
    fields = ["id_vlan", "nom", "reseau", "gateway", "type", "ports", "status"]
    fields.append("switch_name" if "switch_name" in columns else "NULL AS switch_name")
    fields.append("switch_ip"   if "switch_ip"   in columns else "NULL AS switch_ip")
    return fields


# ─── Routes CRUD ─────────────────────────────────────────────────────────────

@vlan_bp.route("/api/vlan", methods=["GET"])
@vlan_bp.route("/vlan",     methods=["GET"])
def get_vlans():
    filter_switch_name = request.args.get("switch_name", "").strip()
    filter_switch_id   = request.args.get("switch_id", "").strip()

    conn = get_db_connection()
    try:
        columns = get_vlan_columns(conn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        where_clauses = []
        params = []

        if filter_switch_name:
            where_clauses.append("switch_name = %s")
            params.append(filter_switch_name)
        elif filter_switch_id:
            cur2 = conn.cursor()
            cur2.execute("SELECT nom FROM switchs WHERE id_switch = %s", (filter_switch_id,))
            sw_row = cur2.fetchone()
            cur2.close()
            if sw_row:
                where_clauses.append("switch_name = %s")
                params.append(sw_row[0])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        cur.execute(f"""
            SELECT {", ".join(get_returning_fields(columns))}
            FROM vlan
            {where_sql}
            ORDER BY id_vlan ASC
        """, params)
        rows  = cur.fetchall()
        vlans = [build_vlan_response(row) for row in rows]
        return jsonify({"success": True, "count": len(vlans), "vlans": vlans})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@vlan_bp.route("/api/switchs", methods=["GET"])
@vlan_bp.route("/switchs",     methods=["GET"])
def get_switchs():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id_switch, nom, ip, status
            FROM switchs
            ORDER BY nom ASC
        """)
        rows = cur.fetchall()
        switchs = [
            {
                "id":     row["id_switch"],
                "nom":    row["nom"],
                "ip":     row["ip"],
                "status": row.get("status") or "Active",
            }
            for row in rows
        ]
        return jsonify({"success": True, "switchs": switchs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ─── Create VLAN (BDD + déploiement SSH automatique) ─────────────────────────

@vlan_bp.route("/api/vlan",                    methods=["POST"])
@vlan_bp.route("/vlan",                        methods=["POST"])
@vlan_bp.route("/api/network/deploy-vlan",     methods=["POST"])
def create_vlan():
    """
    Crée un VLAN en base de données ET le déploie sur le switch via SSH.
    """
    try:
        payload = normalize_vlan_payload(request.get_json())
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    # ── 1. Sauvegarde en BDD ──────────────────────────────────────────────────
    conn = get_db_connection()
    try:
        columns = get_vlan_columns(conn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT 1 FROM vlan WHERE id_vlan = %s", (payload["id_vlan"],))
        if cur.fetchone():
            return jsonify({"success": False, "error": f"Le VLAN {payload['id_vlan']} existe déjà"}), 409

        insert_columns = ["id_vlan", "nom", "reseau", "gateway", "type", "ports", "status"]
        insert_values  = [
            payload["id_vlan"],
            payload["nom"],
            payload["reseau"] or None,
            payload["gateway"] or None,
            payload["type"],
            payload["ports"],
            payload["status"],
        ]

        if "switch_name" in columns:
            insert_columns.append("switch_name")
            insert_values.append(payload["switch_name"])
        if "switch_ip" in columns:
            insert_columns.append("switch_ip")
            insert_values.append(payload["switch_ip"])

        placeholders = ", ".join(["%s"] * len(insert_columns))
        cur.execute(f"""
            INSERT INTO vlan ({", ".join(insert_columns)})
            VALUES ({placeholders})
            RETURNING {", ".join(get_returning_fields(columns))}
        """, insert_values)
        row = cur.fetchone()
        conn.commit()

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

    # ── 2. Déploiement SSH sur le switch ──────────────────────────────────────
    deploy_result = {"success": False, "error": "Déploiement non tenté"}
    try:
        from network.deploy_vlan import run_deploy
        deploy_result = run_deploy(payload["id_vlan"], payload["nom"])
    except ImportError:
        deploy_result = {"success": False, "error": "Module network.deploy_vlan introuvable"}
    except Exception as e:
        deploy_result = {"success": False, "error": str(e)}

    # ── 3. Réponse unifiée ────────────────────────────────────────────────────
    response = {
        "success":     True,
        "message":     "VLAN créé en base de données.",
        "vlan":        build_vlan_response(row),
        "ssh_deploy":  deploy_result,
    }

    if not deploy_result.get("success"):
        response["warning"] = (
            f"VLAN enregistré en BDD mais le déploiement SSH a échoué : "
            f"{deploy_result.get('error', 'Erreur inconnue')}"
        )

    return jsonify(response), 201


# ─── PUT ──────────────────────────────────────────────────────────────────────

@vlan_bp.route("/api/vlan/<int:id_vlan>", methods=["PUT"])
@vlan_bp.route("/vlan/<int:id_vlan>",     methods=["PUT"])
def update_vlan(id_vlan):
    try:
        payload = normalize_vlan_payload(request.get_json() or {}, forced_vlan_id=id_vlan)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    conn = get_db_connection()
    try:
        columns = get_vlan_columns(conn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        set_clauses = ["nom = %s", "reseau = %s", "gateway = %s", "type = %s", "ports = %s", "status = %s"]
        values      = [payload["nom"], payload["reseau"] or None, payload["gateway"] or None,
                       payload["type"], payload["ports"], payload["status"]]

        if "switch_name" in columns:
            set_clauses.append("switch_name = %s")
            values.append(payload["switch_name"])
        if "switch_ip" in columns:
            set_clauses.append("switch_ip = %s")
            values.append(payload["switch_ip"])

        values.append(id_vlan)
        cur.execute(f"""
            UPDATE vlan
            SET {", ".join(set_clauses)}
            WHERE id_vlan = %s
            RETURNING {", ".join(get_returning_fields(columns))}
        """, values)
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return jsonify({"success": False, "error": "VLAN introuvable"}), 404

        conn.commit()
        return jsonify({"success": True, "message": f"VLAN {id_vlan} mis à jour.", "vlan": build_vlan_response(row)})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ─── DELETE (BDD + suppression SSH sur le switch) ────────────────────────────

@vlan_bp.route("/api/vlan/<int:id_vlan>", methods=["DELETE"])
@vlan_bp.route("/vlan/<int:id_vlan>",     methods=["DELETE"])
def delete_vlan(id_vlan):
    """
    Supprime le VLAN de la base de données ET l'efface du switch via SSH.
    Commandes envoyées sur le switch :
        conf t
        no vlan <id>
        no interface vlan <id>    (supprime le SVI / gateway)
        end
        write memory
    """
    conn = get_db_connection()
    try:
        columns = get_vlan_columns(conn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(f"""
            DELETE FROM vlan WHERE id_vlan = %s
            RETURNING {", ".join(get_returning_fields(columns))}
        """, (id_vlan,))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return jsonify({"success": False, "error": "VLAN introuvable"}), 404

        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

    vlan_data = build_vlan_response(row)

    # ── Suppression SSH sur le switch ─────────────────────────────────────────
    ssh_result = {"success": False, "error": "Suppression SSH non tentée"}
    try:
        from network.deploy_vlan import run_delete
        ssh_result = run_delete(id_vlan)
    except ImportError:
        # Fallback : si run_delete n'existe pas, on tente directement via Netmiko
        try:
            ssh_result = _ssh_delete_vlan(id_vlan)
        except Exception as e2:
            ssh_result = {"success": False, "error": str(e2)}
    except Exception as e:
        ssh_result = {"success": False, "error": str(e)}

    response = {
        "success":    True,
        "message":    f"VLAN {id_vlan} supprimé de la base de données.",
        "vlan":       vlan_data,
        "ssh_delete": ssh_result,
    }

    if not ssh_result.get("success"):
        response["warning"] = (
            f"VLAN supprimé en BDD mais la suppression SSH a échoué : "
            f"{ssh_result.get('error', 'Erreur inconnue')}"
        )

    return jsonify(response)


def _ssh_delete_vlan(id_vlan: int) -> dict:
    """
    Connexion SSH directe (Netmiko) pour supprimer un VLAN du switch.
    Lit les credentials depuis network/hosts.yaml (même logique que deploy_vlan).
    """
    import yaml, os
    from netmiko import ConnectHandler

    # Chercher hosts.yaml dans les chemins courants
    base_dir = os.path.dirname(os.path.abspath(__file__))
    hosts_path = None
    for candidate in [
        os.path.join(base_dir, "network", "hosts.yaml"),
        os.path.join(base_dir, "hosts.yaml"),
        os.path.join(os.getcwd(), "network", "hosts.yaml"),
    ]:
        if os.path.exists(candidate):
            hosts_path = candidate
            break

    if not hosts_path:
        return {"success": False, "error": "hosts.yaml introuvable — impossible de se connecter au switch"}

    with open(hosts_path, "r") as f:
        hosts_data = yaml.safe_load(f)

    # Supports both list and dict formats
    if isinstance(hosts_data, list):
        host_cfg = hosts_data[0]
    elif isinstance(hosts_data, dict):
        # Format: {switch_cible: {...}} or direct dict
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
        return {"success": False, "error": "Credentials SSH incomplets dans hosts.yaml"}

    commands = [
        "conf t",
        f"no vlan {id_vlan}",
        f"no interface vlan {id_vlan}",
        "end",
        "write memory",
    ]

    net_connect = ConnectHandler(**device)
    try:
        if device["secret"]:
            net_connect.enable()
        output = net_connect.send_config_set(commands[1:-1])  # entre conf t et end
        net_connect.send_command("end")
        net_connect.send_command("write memory")
    finally:
        net_connect.disconnect()

    return {
        "success":  True,
        "message":  f"VLAN {id_vlan} supprimé du switch avec succès.",
        "commands": commands,
        "output":   output,
    }