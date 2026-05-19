from flask import Blueprint, jsonify, request
from Database.db import get_db_connection
import psycopg2.extras
import re

logs_bp = Blueprint("logs", __name__)

# ─────────────────────────────────────────────────────────────────────────────
# ROUTE : GET /api/logs
# Agrège les alertes : N alertes SSH → 1 ligne de log
# Groupement par (attack_type, source_ip, destination_ip, protocol)
# ─────────────────────────────────────────────────────────────────────────────
@logs_bp.route("/api/logs", methods=["GET"])
def get_logs():
    """
    Retourne les logs agrégés depuis la table alertes.
    Plusieurs alertes du même type/source/dest sont fusionnées en 1 ligne.

    Paramètres GET :
      - severity  : critical | medium | low
      - search    : texte libre (IP, type d'attaque, protocole)
      - sort      : newest | oldest | count_desc | count_asc
      - month     : YYYY-MM
      - limit     : int (défaut 100)
      - offset    : int (défaut 0)
    """
    severity = request.args.get("severity", "").strip()
    search   = request.args.get("search", "").strip()
    sort     = request.args.get("sort", "newest")
    month    = request.args.get("month", "").strip()

    try:
        limit = max(1, int(request.args.get("limit", 100)))
    except ValueError:
        limit = 100
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        offset = 0

    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ── Conditions WHERE sur la table brute ──────────────────────────────
        conditions, params = [], []

        if severity:
            sev_map = {
                "critical": ("critical", "critique", "high", "élevée", "elevee"),
                "medium":   ("medium", "moyen", "moyenne"),
                "low":      ("low", "faible", "basse"),
            }
            db_values    = sev_map.get(severity, (severity,))
            placeholders = ",".join(["%s"] * len(db_values))
            conditions.append(f"LOWER(severity) IN ({placeholders})")
            params.extend(db_values)

        if search:
            date_match = re.match(r'^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$', search)
            if date_match:
                yr, mo, dy = date_match.groups()
                if dy:
                    conditions.append("DATE(timestamp) = %s::date")
                    params.append(f"{yr}-{mo}-{dy}")
                elif mo:
                    conditions.append(
                        "EXTRACT(YEAR FROM timestamp)=%s AND EXTRACT(MONTH FROM timestamp)=%s"
                    )
                    params.extend([int(yr), int(mo)])
                else:
                    conditions.append("EXTRACT(YEAR FROM timestamp)=%s")
                    params.append(int(yr))
            else:
                like = f"%{search.lower()}%"
                conditions.append(
                    "(LOWER(attack_type) LIKE %s OR LOWER(source_ip) LIKE %s "
                    "OR LOWER(destination_ip) LIKE %s OR LOWER(protocol) LIKE %s)"
                )
                params.extend([like, like, like, like])

        if month and re.match(r'^\d{4}-\d{2}$', month):
            yr, mo = month.split("-")
            conditions.append(
                "EXTRACT(YEAR FROM timestamp)=%s AND EXTRACT(MONTH FROM timestamp)=%s"
            )
            params.extend([int(yr), int(mo)])

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # ── Tri ───────────────────────────────────────────────────────────────
        order_map = {
            "newest":     "last_seen DESC",
            "oldest":     "first_seen ASC",
            "count_desc": "count DESC",
            "count_asc":  "count ASC",
        }
        order_clause = order_map.get(sort, "last_seen DESC")

        # ── Comptage des groupes distincts ────────────────────────────────────
        count_query = f"""
            SELECT COUNT(*) AS total FROM (
                SELECT 1
                FROM alertes
                {where_clause}
                GROUP BY attack_type, source_ip, destination_ip, protocol
            ) sub
        """
        cur.execute(count_query, params)
        total_row = cur.fetchone()
        total = int(total_row["total"]) if total_row else 0

        # ── Requête d'agrégation principale ──────────────────────────────────
        agg_query = f"""
            SELECT
                attack_type                             AS name,
                protocol                                AS proto,
                source_ip                               AS src_ip,
                destination_ip                          AS dst_ip,
                MIN(source_port)                        AS src_port,
                MIN(destination_port)                   AS dst_port,
                COUNT(*)                                AS count,
                MIN(timestamp)                          AS first_seen,
                MAX(timestamp)                          AS last_seen,
                -- Sévérité la plus haute du groupe
                MAX(CASE
                    WHEN LOWER(severity) IN ('critical','critique','high','élevée','elevee') THEN 3
                    WHEN LOWER(severity) IN ('medium','moyen','moyenne')                     THEN 2
                    ELSE 1
                END) AS sev_rank,
                -- IDs des alertes brutes (pour drill-down)
                ARRAY_AGG(id ORDER BY timestamp DESC)   AS alert_ids,
                -- IPs destination distinctes
                ARRAY_AGG(DISTINCT destination_ip)      AS dst_ips,
                -- Ports source/dest distincts
                ARRAY_AGG(DISTINCT source_port::text) FILTER (WHERE source_port IS NOT NULL) AS src_ports,
                ARRAY_AGG(DISTINCT destination_port::text) FILTER (WHERE destination_port IS NOT NULL) AS dst_ports,
                -- Moteur de détection le plus fréquent
                MODE() WITHIN GROUP (ORDER BY detection_engine) AS engine
            FROM alertes
            {where_clause}
            GROUP BY attack_type, source_ip, destination_ip, protocol
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        """
        params_with_pg = params + [limit, offset]
        cur.execute(agg_query, params_with_pg)
        rows = cur.fetchall()

        # ── Stats globales ────────────────────────────────────────────────────
        cur.execute(f"""
            SELECT
                COUNT(*)                                                                   AS raw_total,
                COUNT(*) FILTER (WHERE LOWER(severity) IN
                    ('critical','critique','high','élevée','elevee'))                       AS critical,
                COUNT(*) FILTER (WHERE LOWER(severity) IN ('medium','moyen','moyenne'))    AS medium,
                COUNT(*) FILTER (WHERE LOWER(severity) IN ('low','faible','basse'))        AS low,
                COUNT(DISTINCT source_ip)                                                  AS unique_ips,
                COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '1 minute')          AS rate_per_min
            FROM alertes
            {where_clause}
        """, params)
        stats_row = cur.fetchone()
        stats = dict(stats_row) if stats_row else {}

        # ── Sérialisation des lignes ──────────────────────────────────────────
        sev_rank_map = {3: "critical", 2: "medium", 1: "low"}
        logs = []
        for row in rows:
            sev = sev_rank_map.get(int(row["sev_rank"]), "low")
            logs.append({
                "name":       row["name"] or "Unknown",
                "proto":      (row["proto"] or "N/A").upper(),
                "src_ip":     row["src_ip"] or "N/A",
                "dst_ip":     row["dst_ip"] or "N/A",
                "src_port":   str(row["src_port"]) if row["src_port"] else "—",
                "dst_port":   str(row["dst_port"]) if row["dst_port"] else "—",
                "count":      int(row["count"]),
                "severity":   sev,
                "first_seen": row["first_seen"].isoformat() if row["first_seen"] else None,
                "last_seen":  row["last_seen"].isoformat()  if row["last_seen"]  else None,
                "alert_ids":  (row["alert_ids"] or [])[:50],   # limiter à 50 IDs
                "dst_ips":    list(row["dst_ips"] or []),
                "src_ports":  list(row["src_ports"] or []),
                "dst_ports":  list(row["dst_ports"] or []),
                "engine":     row["engine"] or "Snort",
            })

        return jsonify({
            "success":          True,
            "total":            total,          # nombre de groupes
            "count":            len(logs),
            "limit":            limit,
            "offset":           offset,
            "raw_total":        int(stats.get("raw_total", 0)),
            "stats": {
                "critical":     int(stats.get("critical", 0)),
                "medium":       int(stats.get("medium", 0)),
                "low":          int(stats.get("low", 0)),
                "unique_ips":   int(stats.get("unique_ips", 0)),
                "rate_per_min": int(stats.get("rate_per_min", 0)),
            },
            "logs": logs,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE : GET /api/logs/<name>/alerts
# Retourne les alertes brutes d'un groupe (drill-down)
# ─────────────────────────────────────────────────────────────────────────────
@logs_bp.route("/api/logs/drill", methods=["GET"])
def drill_down():
    """
    Retourne les alertes brutes pour un groupe donné.
    Paramètres : name, src_ip, dst_ip, proto
    """
    name   = request.args.get("name", "").strip()
    src_ip = request.args.get("src_ip", "").strip()
    dst_ip = request.args.get("dst_ip", "").strip()
    proto  = request.args.get("proto", "").strip()

    if not name:
        return jsonify({"success": False, "error": "Paramètre 'name' requis"}), 400

    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        conditions = ["LOWER(attack_type) = LOWER(%s)"]
        params     = [name]

        if src_ip:
            conditions.append("source_ip = %s")
            params.append(src_ip)
        if dst_ip:
            conditions.append("destination_ip = %s")
            params.append(dst_ip)
        if proto:
            conditions.append("LOWER(protocol) = LOWER(%s)")
            params.append(proto)

        cur.execute(f"""
            SELECT id, timestamp, source_ip, destination_ip,
                   attack_type, severity, protocol,
                   source_port, destination_port,
                   detection_engine, details, loss, volume, service
            FROM alertes
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp DESC
            LIMIT 200
        """, params)

        rows = cur.fetchall()

        def normalize_sev(s):
            s = (s or "").lower()
            if s in ("critical","critique","high","élevée","elevee"): return "critical"
            if s in ("medium","moyen","moyenne"): return "medium"
            return "low"

        alerts = [{
            "id":          r["id"],
            "timestamp":   r["timestamp"].isoformat() if r["timestamp"] else None,
            "src":         f"{r['source_ip']}:{r['source_port']}" if r["source_port"] else r["source_ip"],
            "dst":         f"{r['destination_ip']}:{r['destination_port']}" if r["destination_port"] else r["destination_ip"],
            "name":        r["attack_type"] or "Unknown",
            "proto":       r["protocol"] or "N/A",
            "severity":    normalize_sev(r["severity"]),
            "engine":      r["detection_engine"],
            "details":     r["details"],
        } for r in rows]

        return jsonify({"success": True, "count": len(alerts), "alerts": alerts})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE : GET /api/logs/months
# Liste des mois disponibles (pour le sélecteur)
# ─────────────────────────────────────────────────────────────────────────────
@logs_bp.route("/api/logs/months", methods=["GET"])
def get_log_months():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT DISTINCT
                TO_CHAR(timestamp, 'YYYY-MM') AS month
            FROM alertes
            WHERE timestamp IS NOT NULL
            ORDER BY month DESC
        """)
        months = [r["month"] for r in cur.fetchall()]
        return jsonify({"success": True, "months": months})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()