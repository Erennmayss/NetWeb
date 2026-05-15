from flask import Blueprint, jsonify, request
from Database.db import get_db_connection
import psycopg2.extras
import re

traffic_bp = Blueprint("traffic", __name__)


# ─────────────────────────────────────────────
# GET /api/traffic/stats
# Cartes statistiques : total alertes, taux perte, sessions TCP, protocoles
# ─────────────────────────────────────────────
@traffic_bp.route("/api/traffic/stats", methods=["GET"])
def get_traffic_stats():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT
                COUNT(*)                                                                AS total_alerts,
                COUNT(*) FILTER (WHERE LOWER(severity) IN ('critical','critique','high','élevée','elevee')) AS critical_count,
                COUNT(*) FILTER (WHERE LOWER(protocol) = 'tcp')                        AS tcp_sessions,
                COUNT(*) FILTER (WHERE LOWER(protocol) = 'udp')                        AS udp_sessions,
                COUNT(*) FILTER (WHERE LOWER(protocol) = 'icmp')                       AS icmp_sessions,
                COUNT(DISTINCT source_ip)                                               AS unique_ips,

                -- Récupérer toutes les valeurs de volume et loss brutes
                volume,
                loss,

                COUNT(*) AS total_count

            FROM alertes
            GROUP BY volume, loss
        """)

        # On refait la requête correctement pour avoir toutes les lignes
        cur.execute("""
            SELECT volume, loss FROM alertes
        """)
        rows_all = cur.fetchall()

        # Parser RX et TX depuis la colonne volume (format: "RX:0.05MB TX:0MB")
        rx_total = 0.0
        tx_total = 0.0
        loss_total = 0.0
        count_total = len(rows_all) or 1

        for r in rows_all:
            vol_str = r["volume"] or ""
            loss_str = r["loss"] or ""

            # Extraire RX
            rx_match = re.search(r'RX:\s*([\d.]+)', vol_str, re.IGNORECASE)
            if rx_match:
                rx_total += float(rx_match.group(1))

            # Extraire TX
            tx_match = re.search(r'TX:\s*([\d.]+)', vol_str, re.IGNORECASE)
            if tx_match:
                tx_total += float(tx_match.group(1))

            # Extraire loss
            loss_match = re.search(r'([\d.]+)', loss_str)
            if loss_match:
                loss_total += float(loss_match.group(1))

        # Maintenant récupérer les stats agrégées
        cur.execute("""
            SELECT
                COUNT(*)                                                                AS total_alerts,
                COUNT(*) FILTER (WHERE LOWER(severity) IN ('critical','critique','high','élevée','elevee')) AS critical_count,
                COUNT(*) FILTER (WHERE LOWER(protocol) = 'tcp')                        AS tcp_sessions,
                COUNT(*) FILTER (WHERE LOWER(protocol) = 'udp')                        AS udp_sessions,
                COUNT(*) FILTER (WHERE LOWER(protocol) = 'icmp')                       AS icmp_sessions,
                COUNT(DISTINCT source_ip)                                               AS unique_ips,
                COUNT(*)                                                                AS total_count
            FROM alertes
        """)
        row = cur.fetchone()

        total = row["tcp_sessions"] + row["udp_sessions"] + row["icmp_sessions"]
        tcp_pct  = round(row["tcp_sessions"]  / total * 100) if total > 0 else 0
        udp_pct  = round(row["udp_sessions"]  / total * 100) if total > 0 else 0
        icmp_pct = round(row["icmp_sessions"] / total * 100) if total > 0 else 0

        total_count = row["total_count"] or 1

        # RX = somme(RX) / total
        rx_mb = rx_total / total_count

        # TX = somme(TX) / total
        tx_mb = tx_total / total_count

        # Volume total = (RX + TX) / 2
        vol_mb = (rx_mb + tx_mb) / 2

        # Taux de perte = somme(loss) / total
        loss_rate = loss_total / total_count

        def fmt_mb(mb):
            if mb >= 1024:
                return f"{mb/1024:.1f} GB"
            return f"{mb:.2f} MB"

        return jsonify({
            "success": True,
            "stats": {
                "total_alerts":   row["total_alerts"],
                "critical_count": row["critical_count"],
                "tcp_sessions":   row["tcp_sessions"],
                "udp_sessions":   row["udp_sessions"],
                "icmp_sessions":  row["icmp_sessions"],
                "unique_ips":     row["unique_ips"],
                "avg_loss":       f"{loss_rate:.2f}%",
                # Nouvelles valeurs pour "Volume de données"
                "rx_total":       fmt_mb(rx_mb),
                "tx_total":       fmt_mb(tx_mb),
                "volume_total":   fmt_mb(vol_mb),
                "protocol_distribution": [
                    {"name": "TCP",  "value": tcp_pct,  "color": "#6366f1"},
                    {"name": "UDP",  "value": udp_pct,  "color": "#22c55e"},
                    {"name": "ICMP", "value": icmp_pct, "color": "#f59e0b"},
                ]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────
# GET /api/traffic/top-ips?limit=5
# Top IPs par volume de trafic
# ─────────────────────────────────────────────
@traffic_bp.route("/api/traffic/top-ips", methods=["GET"])
def get_top_ips():
    try:
        limit = int(request.args.get("limit", 5))
    except ValueError:
        limit = 5

    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                source_ip                                        AS ip,
                COUNT(*)                                         AS total,
                COUNT(*) FILTER (WHERE LOWER(protocol)='tcp')   AS tcp,
                COUNT(*) FILTER (WHERE LOWER(protocol)='udp')   AS udp,
                COUNT(*) FILTER (WHERE LOWER(protocol)='icmp')  AS icmp,
                MAX(timestamp)                                   AS last_seen,
                MODE() WITHIN GROUP (ORDER BY protocol)         AS main_protocol,
                array_agg(volume)                               AS volumes,
                MODE() WITHIN GROUP (ORDER BY source_port::text)      AS main_src_port,
                MODE() WITHIN GROUP (ORDER BY destination_port::text) AS main_dst_port
            FROM alertes
            GROUP BY source_ip
            ORDER BY total DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()

        total_all = sum(r["total"] for r in rows) or 1
        result = []
        for r in rows:
            share = round(r["total"] / total_all * 100)

            # Parser RX+TX depuis les volumes de cette IP
            total_vol = 0.0
            for vol_str in (r["volumes"] or []):
                rx_m = re.search(r'RX:\s*([\d.]+)', vol_str or "", re.IGNORECASE)
                tx_m = re.search(r'TX:\s*([\d.]+)', vol_str or "", re.IGNORECASE)
                if rx_m: total_vol += float(rx_m.group(1))
                if tx_m: total_vol += float(tx_m.group(1))

            vol_str_fmt = f"{total_vol/1024:.1f} GB" if total_vol >= 1024 else f"{total_vol:.2f} MB"

            result.append({
                "ip":           r["ip"],
                "volume":       vol_str_fmt,
                "packets":      f"{r['total']:,}".replace(",", " "),
                "tcp":          r["tcp"],
                "udp":          r["udp"],
                "icmp":         r["icmp"],
                "protocol":     (r["main_protocol"] or "TCP").upper(),
                "share":        f"{share}%",
                "lastActivity": r["last_seen"].strftime("%H:%M:%S") if r["last_seen"] else "--",
                "src_port":     r["main_src_port"] or "--",
                "dst_port":     r["main_dst_port"] or "--",
            })

        return jsonify({"success": True, "ips": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────
# GET /api/traffic/ip-details
# Toutes les IPs avec détails TCP/UDP/ICMP (page Adresses IP)
# ─────────────────────────────────────────────
@traffic_bp.route("/api/traffic/ip-details", methods=["GET"])
def get_ip_details():
    search = request.args.get("search", "").strip()
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        where_clause = "WHERE source_ip ILIKE %s" if search else ""
        query = """
            SELECT
                source_ip                                        AS ip,
                COUNT(*) FILTER (WHERE LOWER(protocol)='tcp')   AS tcp,
                COUNT(*) FILTER (WHERE LOWER(protocol)='udp')   AS udp,
                COUNT(*) FILTER (WHERE LOWER(protocol)='icmp')  AS icmp,
                MAX(timestamp)                                   AS last_seen,
                array_agg(volume)                               AS volumes
            FROM alertes
            {}
            GROUP BY source_ip
            ORDER BY (COUNT(*) FILTER (WHERE LOWER(protocol)='tcp') +
                      COUNT(*) FILTER (WHERE LOWER(protocol)='udp') +
                      COUNT(*) FILTER (WHERE LOWER(protocol)='icmp')) DESC
        """.format(where_clause)

        params = (f"%{search}%",) if search else ()
        cur.execute(query, params)
        rows = cur.fetchall()

        result = []
        for r in rows:
            total_vol = 0.0
            for vol_str in (r["volumes"] or []):
                rx_m = re.search(r'RX:\s*([\d.]+)', vol_str or "", re.IGNORECASE)
                tx_m = re.search(r'TX:\s*([\d.]+)', vol_str or "", re.IGNORECASE)
                if rx_m: total_vol += float(rx_m.group(1))
                if tx_m: total_vol += float(tx_m.group(1))

            vol_str_fmt = f"{total_vol/1024:.1f} GB" if total_vol >= 1024 else f"{total_vol:.2f} MB"

            result.append({
                "ip":           r["ip"],
                "tcp":          r["tcp"],
                "udp":          r["udp"],
                "icmp":         r["icmp"],
                "volume":       vol_str_fmt,
                "lastActivity": r["last_seen"].strftime("%H:%M:%S") if r["last_seen"] else "--"
            })

        return jsonify({"success": True, "ips": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────
# GET /api/traffic/port-overview
# Top ports source et destination (Vue d'ensemble)
# ─────────────────────────────────────────────
@traffic_bp.route("/api/traffic/port-overview", methods=["GET"])
def get_port_overview():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Top 5 ports source
        cur.execute("""
            SELECT source_port AS port, COUNT(*) AS cnt
            FROM alertes
            WHERE source_port IS NOT NULL
            GROUP BY source_port
            ORDER BY cnt DESC
            LIMIT 5
        """)
        src_rows = cur.fetchall()

        # Top 5 ports destination
        cur.execute("""
            SELECT destination_port AS port, service, COUNT(*) AS cnt
            FROM alertes
            WHERE destination_port IS NOT NULL
            GROUP BY destination_port, service
            ORDER BY cnt DESC
            LIMIT 5
        """)
        dst_rows = cur.fetchall()

        max_src = max((r["cnt"] for r in src_rows), default=1)
        max_dst = max((r["cnt"] for r in dst_rows), default=1)

        return jsonify({
            "success": True,
            "source_ports": [
                {
                    "port":  r["port"],
                    "count": r["cnt"],
                    "pct":   round(r["cnt"] / max_src * 100)
                }
                for r in src_rows
            ],
            "destination_ports": [
                {
                    "port":    r["port"],
                    "service": r["service"] or "Inconnu",
                    "count":   r["cnt"],
                    "pct":     round(r["cnt"] / max_dst * 100)
                }
                for r in dst_rows
            ]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────
# GET /api/traffic/ports
# Top ports TCP et UDP depuis la table alertes
# ─────────────────────────────────────────────
@traffic_bp.route("/api/traffic/ports", methods=["GET"])
def get_ports():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Top ports TCP
        cur.execute("""
            SELECT destination_port AS port, service, COUNT(*) AS cnt
            FROM alertes
            WHERE LOWER(protocol) = 'tcp' AND destination_port IS NOT NULL
            GROUP BY destination_port, service
            ORDER BY cnt DESC
            LIMIT 5
        """)
        tcp_rows = cur.fetchall()

        # Top ports UDP
        cur.execute("""
            SELECT destination_port AS port, service, COUNT(*) AS cnt
            FROM alertes
            WHERE LOWER(protocol) = 'udp' AND destination_port IS NOT NULL
            GROUP BY destination_port, service
            ORDER BY cnt DESC
            LIMIT 5
        """)
        udp_rows = cur.fetchall()

        # Activité ports spécifiques (22, 53, 80)
        cur.execute("""
            SELECT destination_port AS port, COUNT(*) AS cnt
            FROM alertes
            WHERE destination_port IN (22, 53, 80)
            GROUP BY destination_port
        """)
        activity_rows = {r["port"]: r["cnt"] for r in cur.fetchall()}
        max_cnt = max(activity_rows.values(), default=1)

        port_labels = {22: "22 - SSH", 53: "53 - DNS", 80: "80 - HTTP"}
        port_colors = {22: "#6366f1", 53: "#22c55e", 80: "#f59e0b"}
        port_activity = [
            {
                "label": port_labels[p],
                "value": round(activity_rows.get(p, 0) / max_cnt * 100),
                "count": f"{activity_rows.get(p, 0):,} connexions".replace(",", " "),
                "color": port_colors[p]
            }
            for p in [22, 53, 80]
        ]

        def fmt_port(r):
            return {
                "port":    r["port"],
                "service": r["service"] or "Inconnu",
                "count":   f"{r['cnt']:,}".replace(",", " ")
            }

        return jsonify({
            "success": True,
            "tcp_ports":     [fmt_port(r) for r in tcp_rows],
            "udp_ports":     [fmt_port(r) for r in udp_rows],
            "port_activity": port_activity
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()