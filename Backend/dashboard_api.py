import logging
import re

import psycopg2.extras
from flask import Blueprint, jsonify

from Database.alerts import analyze_traffic_status, row_to_alert
from Database.db import get_db_connection

dashboard_bp = Blueprint("dashboard", __name__)
logger = logging.getLogger(__name__)


def _empty_summary(error=None):
    payload = {
        "success": True,
        "stats": {
            "total": 0,
            "critical": 0,
            "medium": 0,
            "low": 0,
            "unique_sources": 0,
            "rate_per_minute": 0,
        },
        "recentAlerts": [],
        "trafficStatus": {"status": "Normal", "color": "#22c55e", "bg": "bg-green"},
        "rulesCount": 0,
        "vlanStats": {"count": 0, "lastCreated": None, "quarantine": None},
        "interfaceStats": {
            "total": 0,
            "up": 0,
            "down": 0,
            "securePorts": 0,
            "hasAlert": False,
        },
        "lastTriggeredRule": None,
        "userActivities": [],
    }
    if error:
        payload["warning"] = error
    return payload


@dashboard_bp.route("/api/dashboard/summary", methods=["GET"])
def dashboard_summary():
    summary = _empty_summary()
    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE LOWER(severity) IN
                    ('critical', 'critique', 'high', 'elevee')) AS critical,
                COUNT(*) FILTER (WHERE LOWER(severity) IN
                    ('medium', 'moyen', 'moyenne')) AS medium,
                COUNT(*) FILTER (WHERE LOWER(severity) IN
                    ('low', 'faible', 'basse')) AS low,
                COUNT(DISTINCT source_ip) AS unique_sources,
                COUNT(*) FILTER (
                    WHERE timestamp >= NOW() - INTERVAL '1 minute'
                ) AS rate_per_minute
            FROM alertes
        """)
        summary["stats"] = dict(cur.fetchone() or summary["stats"])

        cur.execute("""
            SELECT id, timestamp, source_ip, destination_ip,
                   attack_type, severity, detection_engine,
                   details, protocol, source_port, destination_port,
                   loss, volume, service
            FROM alertes
            ORDER BY timestamp DESC
            LIMIT 200
        """)
        alerts = [row_to_alert(row) for row in cur.fetchall()]
        summary["recentAlerts"] = alerts[:5]
        summary["trafficStatus"] = analyze_traffic_status(alerts)

        cur.execute("SELECT COUNT(*) AS count FROM regles")
        summary["rulesCount"] = int((cur.fetchone() or {}).get("count") or 0)

        cur.execute("""
            SELECT id_vlan, nom, reseau, gateway, type, ports, status,
                   switch_name, switch_ip
            FROM vlan
            ORDER BY id_vlan DESC
        """)
        vlans = [dict(row) for row in cur.fetchall()]
        summary["vlanStats"] = {
            "count": len(vlans),
            "lastCreated": vlans[0] if vlans else None,
            "quarantine": next(
                (row for row in vlans if str(row.get("status") or "").lower() == "alert"),
                None,
            ),
        }

        cur.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE UPPER(COALESCE(status, '')) = 'UP') AS up,
                COUNT(*) FILTER (WHERE UPPER(COALESCE(status, '')) <> 'UP') AS down,
                COUNT(*) FILTER (WHERE port_security = TRUE) AS secure_ports,
                BOOL_OR(
                    COALESCE(port_security, FALSE) = FALSE
                    AND UPPER(COALESCE(status, '')) = 'UP'
                ) AS has_alert
            FROM interface
        """)
        interface_row = cur.fetchone() or {}
        summary["interfaceStats"] = {
            "total": int(interface_row.get("total") or 0),
            "up": int(interface_row.get("up") or 0),
            "down": int(interface_row.get("down") or 0),
            "securePorts": int(interface_row.get("secure_ports") or 0),
            "hasAlert": bool(interface_row.get("has_alert") or False),
        }

        cur.execute("""
            SELECT username, action, timestamp
            FROM (
                SELECT username, 'login' AS action, last_login AS timestamp
                FROM utilisateur
                WHERE last_login IS NOT NULL
                UNION ALL
                SELECT username, 'logout' AS action, last_logout AS timestamp
                FROM utilisateur
                WHERE last_logout IS NOT NULL
            ) activity
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        summary["userActivities"] = [
            {
                "username": row["username"],
                "action": row["action"],
                "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
            }
            for row in cur.fetchall()
        ]

        cur.execute("""
            SELECT id, timestamp, attack_type, details, protocol, severity
            FROM alertes
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        last_alert = cur.fetchone()
        if last_alert:
            summary["lastTriggeredRule"] = {
                "name": last_alert.get("attack_type", "Attaque detectee"),
                "action": "ALERT",
                "description": f"Protocole: {last_alert.get('protocol', 'N/A')}",
                "sid": None,
            }

            sid_match = re.search(r"sid:(\d+)", last_alert.get("details", "") or "")
            if sid_match:
                sid = int(sid_match.group(1))
                summary["lastTriggeredRule"]["sid"] = sid
                cur.execute("""
                    SELECT sid, rule, action, protocol, src_ip, dst_ip
                    FROM regles
                    WHERE sid = %s
                """, (sid,))
                db_rule = cur.fetchone()
                if db_rule:
                    msg_match = re.search(r'msg:"(.*?)"', db_rule.get("rule") or "")
                    summary["lastTriggeredRule"] = {
                        "name": msg_match.group(1) if msg_match else f"Regle SID {sid}",
                        "action": (db_rule.get("action") or "alert").upper(),
                        "description": (
                            f"{(db_rule.get('protocol') or 'TCP').upper()} "
                            f"{db_rule.get('src_ip', 'any')} -> "
                            f"{db_rule.get('dst_ip', 'any')}"
                        ),
                        "sid": sid,
                    }

    except Exception as exc:
        logger.exception("Erreur /api/dashboard/summary")
        summary = _empty_summary(str(exc))
    finally:
        if conn:
            conn.close()

    return jsonify(summary)
