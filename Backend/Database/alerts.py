from flask import Blueprint, jsonify, request
from Database.db import get_db_connection
import psycopg2.extras

# ─── Blueprint (pas de Flask() ici, app.py s'en charge) ───
alerts_bp = Blueprint("alerts", __name__)


def row_to_alert(row):
    src = f"{row['source_ip']}:{row['source_port']}" if row['source_port'] else row['source_ip']
    dst = f"{row['destination_ip']}:{row['destination_port']}" if row['destination_port'] else row['destination_ip']

    sev_raw = (row['severity'] or "").lower()
    if sev_raw in ("critical", "critique", "high", "élevée", "elevee"):
        sev = "critical"
    elif sev_raw in ("medium", "moyen", "moyenne"):
        sev = "medium"
    else:
        sev = "low"

    return {
        "id":               row["id"],
        "timestamp":        row["timestamp"].isoformat() if row["timestamp"] else None,
        "src":              src,
        "dst":              dst,
        "source_ip":        row["source_ip"],
        "destination_ip":   row["destination_ip"],
        "source_port":      row["source_port"],
        "destination_port": row["destination_port"],
        "name":             row["attack_type"] or "Unknown",
        "proto":            row["protocol"] or "N/A",
        "severity":         sev,
        "detection_engine": row["detection_engine"],
        "details":          row["details"],
        "loss":             row["loss"],
        "volume":           row["volume"],
        "service":          row["service"],
        "sid":              f"1:{row['id']}",
        "rule":             row["details"] or "",
        "payload":          row["details"] or "",
    }


@alerts_bp.route("/api/alerts", methods=["GET"])
def get_alerts():
    severity = request.args.get("severity")
    search   = request.args.get("search", "").strip()
    sort     = request.args.get("sort", "newest")
    try:
        limit = int(request.args.get("limit", 500))
    except ValueError:
        limit = 500

    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        conditions, params = [], []

        if severity:
            sev_map = {
                "critical": ("critical", "critique", "high", "élevée", "elevee"),
                "medium":   ("medium", "moyen", "moyenne"),
                "low":      ("low", "faible", "basse"),
            }
            db_values = sev_map.get(severity, (severity,))
            placeholders = ",".join(["%s"] * len(db_values))
            conditions.append(f"LOWER(severity) IN ({placeholders})")
            params.extend(db_values)

        if search:
            conditions.append(
                "(LOWER(attack_type) LIKE %s OR LOWER(source_ip) LIKE %s "
                "OR LOWER(destination_ip) LIKE %s OR LOWER(protocol) LIKE %s)"
            )
            like = f"%{search.lower()}%"
            params.extend([like, like, like, like])

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        order_map = {"newest": "timestamp DESC", "oldest": "timestamp ASC", "sev": "severity ASC, timestamp DESC"}
        order_clause = order_map.get(sort, "timestamp DESC")

        query = f"""
            SELECT id, timestamp, source_ip, destination_ip,
                   attack_type, severity, detection_engine,
                   details, protocol, source_port, destination_port,
                   loss, volume, service
            FROM alertes
            {where_clause}
            ORDER BY {order_clause}
            LIMIT %s
        """
        params.append(limit)
        cur.execute(query, params)
        rows = cur.fetchall()
        alerts = [row_to_alert(r) for r in rows]
        return jsonify({"success": True, "count": len(alerts), "alerts": alerts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@alerts_bp.route("/api/alerts/recent", methods=["GET"])
def get_recent_alerts():
    try:
        minutes = int(request.args.get("minutes", 1))
    except ValueError:
        minutes = 1

    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, timestamp, source_ip, destination_ip,
                   attack_type, severity, detection_engine,
                   details, protocol, source_port, destination_port,
                   loss, volume, service
            FROM alertes
            WHERE timestamp >= NOW() - INTERVAL '%s minutes'
            ORDER BY timestamp DESC
            LIMIT 100
        """, (minutes,))
        rows = cur.fetchall()
        alerts = [row_to_alert(r) for r in rows]
        return jsonify({"success": True, "count": len(alerts), "alerts": alerts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@alerts_bp.route("/api/alerts/<int:alert_id>", methods=["GET"])
def get_alert(alert_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, timestamp, source_ip, destination_ip,
                   attack_type, severity, detection_engine,
                   details, protocol, source_port, destination_port,
                   loss, volume, service
            FROM alertes WHERE id = %s
        """, (alert_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Alerte introuvable"}), 404
        return jsonify({"success": True, "alert": row_to_alert(row)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@alerts_bp.route("/api/stats", methods=["GET"])
def get_stats():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                COUNT(*)                                                               AS total,
                COUNT(*) FILTER (WHERE LOWER(severity) IN
                    ('critical','critique','high','élevée','elevee'))                  AS critical,
                COUNT(*) FILTER (WHERE LOWER(severity) IN ('medium','moyen','moyenne')) AS medium,
                COUNT(*) FILTER (WHERE LOWER(severity) IN ('low','faible','basse'))    AS low,
                COUNT(DISTINCT source_ip)                                              AS unique_sources,
                COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '1 minute')      AS rate_per_minute
            FROM alertes
        """)
        row = cur.fetchone()
        return jsonify({"success": True, "stats": dict(row)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close
        
@alerts_bp.route("/api/regles/by-message", methods=["GET"])
def get_regle_by_message():
    """Cherche dans la table regles par le champ message (correspondant à attack_type)"""
    message = request.args.get("message", "").strip()
    if not message:
        return jsonify({"success": False, "error": "Paramètre 'message' manquant"}), 400

    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, sid, message, protocol, src_ip, src_port,
                   dst_ip, dst_port, action, rule
            FROM regles
            WHERE LOWER(message) = LOWER(%s)
            LIMIT 1
        """, (message,))
        row = cur.fetchone()
        if not row:
            return jsonify({"success": True, "found": False, "regle": None})
        return jsonify({"success": True, "found": True, "regle": dict(row)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@alerts_bp.route("/api/last-triggered-rule", methods=["GET"])
def get_last_triggered_rule():
    """Récupère la dernière alerte et retourne les infos de la règle Snort correspondante"""
    import re
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Récupérer la dernière alerte
        cur.execute("""
            SELECT 
                id, 
                timestamp,
                attack_type,
                details,
                protocol,
                severity
            FROM alertes 
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        last_alert = cur.fetchone()
        
        if not last_alert:
            return jsonify({
                "success": True,
                "has_alert": False,
                "rule": None,
                "message": "Aucune alerte détectée"
            })
        
        # Extraire le SID depuis details ou attack_type
        details = last_alert.get('details', '')
        sid_match = re.search(r'sid:(\d+)', details)
        
        rule_info = {
            "name": last_alert.get('attack_type', 'Attaque détectée'),
            "action": "ALERT",
            "description": f"Protocole: {last_alert.get('protocol', 'N/A')}",
            "sid": None
        }
        
        if sid_match:
            sid = int(sid_match.group(1))
            rule_info["sid"] = sid
            
            # Chercher la règle correspondante
            cur.execute("""
                SELECT sid, rule, action, protocol, src_ip, dst_ip
                FROM regles 
                WHERE sid = %s
            """, (sid,))
            db_rule = cur.fetchone()
            
            if db_rule:
                msg_match = re.search(r'msg:"(.*?)"', db_rule['rule'] or '')
                rule_info["name"] = msg_match.group(1) if msg_match else f"Règle SID {sid}"
                rule_info["action"] = db_rule.get('action', 'alert').upper()
                rule_info["description"] = f"{db_rule.get('protocol', 'TCP').upper()} {db_rule.get('src_ip', 'any')} → {db_rule.get('dst_ip', 'any')}"
        
        return jsonify({
            "success": True,
            "has_alert": True,
            "rule": rule_info,
            "alert_timestamp": last_alert['timestamp'].isoformat() if last_alert['timestamp'] else None
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()