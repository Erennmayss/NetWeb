from flask import Blueprint, jsonify, request, g
from Database.db import get_db_connection
import psycopg2.extras
from datetime import datetime
import re

logs_bp = Blueprint("logs", __name__)


# ─── Création automatique de la table audit_logs ──────────────────────────────

def ensure_audit_table():
    """Crée la table audit_logs si elle n'existe pas encore."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id          SERIAL PRIMARY KEY,
                timestamp   TIMESTAMPTZ DEFAULT NOW(),
                actor       VARCHAR(100) NOT NULL DEFAULT 'system',
                role        VARCHAR(50)  DEFAULT 'unknown',
                action      VARCHAR(100) NOT NULL,
                category    VARCHAR(50)  NOT NULL DEFAULT 'system',
                target      TEXT,
                details     TEXT,
                severity    VARCHAR(20)  DEFAULT 'Info',
                ip_address  VARCHAR(45),
                success     BOOLEAN      DEFAULT TRUE
            )
        """)
        conn.commit()
    except Exception as e:
        print(f"⚠️  audit_logs table error: {e}")
        conn.rollback()
    finally:
        conn.close()


# ─── Fonction centrale : écrire un log d'audit ───────────────────────────────

def write_audit_log(action, category, target=None, details=None,
                    severity="Info", success=True, actor=None, role=None, ip_address=None):
    """
    Enregistre un événement dans audit_logs.
    Peut être appelée depuis n'importe quel blueprint.
    """
    # Tenter de récupérer l'acteur depuis les headers de la requête courante
    if actor is None:
        try:
            auth_header = request.headers.get("Authorization", "")
            # Format: "Bearer <token>" ou "Basic <base64>"
            # On extrait le nom si dispo dans g (Flask request context)
            actor = getattr(g, "current_user", None) or "system"
            if hasattr(actor, "username"):
                role = actor.role if hasattr(actor, "role") else role
                actor = actor.username
        except RuntimeError:
            actor = "system"

    if ip_address is None:
        try:
            ip_address = request.remote_addr
        except RuntimeError:
            ip_address = None

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_logs
                (actor, role, action, category, target, details, severity, ip_address, success)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            str(actor or "system")[:100],
            str(role or "unknown")[:50],
            str(action)[:100],
            str(category)[:50],
            str(target)[:500] if target else None,
            str(details)[:2000] if details else None,
            str(severity)[:20],
            str(ip_address)[:45] if ip_address else None,
            bool(success),
        ))
        conn.commit()
    except Exception as e:
        print(f"⚠️  Audit log write error: {e}")
        conn.rollback()
    finally:
        conn.close()


# ─── Routes API ───────────────────────────────────────────────────────────────

@logs_bp.route("/api/audit-logs", methods=["GET"])
def get_audit_logs():
    """
    Retourne les logs d'audit avec filtres optionnels.
    Query params: category, severity, actor, search, limit, sort
    """
    ensure_audit_table()

    category = request.args.get("category", "").strip()
    severity = request.args.get("severity", "").strip()
    actor    = request.args.get("actor", "").strip()
    search   = request.args.get("search", "").strip()
    sort     = request.args.get("sort", "newest")
    try:
        limit = int(request.args.get("limit", 200))
    except ValueError:
        limit = 200

    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        conditions, params = [], []

        if category:
            conditions.append("LOWER(category) = %s")
            params.append(category.lower())

        if severity:
            conditions.append("LOWER(severity) = %s")
            params.append(severity.lower())

        if actor:
            conditions.append("LOWER(actor) LIKE %s")
            params.append(f"%{actor.lower()}%")

        if search:
            conditions.append("""
                (LOWER(actor)   LIKE %s OR LOWER(action) LIKE %s
              OR LOWER(target)  LIKE %s OR LOWER(details) LIKE %s
              OR LOWER(category) LIKE %s)
            """)
            like = f"%{search.lower()}%"
            params.extend([like, like, like, like, like])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        order = "timestamp DESC" if sort == "newest" else "timestamp ASC"

        cur.execute(f"""
            SELECT id, timestamp, actor, role, action, category,
                   target, details, severity, ip_address, success
            FROM audit_logs
            {where}
            ORDER BY {order}
            LIMIT %s
        """, params + [limit])

        rows = cur.fetchall()

        logs = []
        for r in rows:
            logs.append({
                "id":         r["id"],
                "date":       r["timestamp"].strftime("%d/%m/%Y %H:%M:%S") if r["timestamp"] else "--",
                "timestamp":  r["timestamp"].isoformat() if r["timestamp"] else None,
                "actor":      r["actor"],
                "role":       r["role"],
                "action":     r["action"],
                "category":   r["category"],
                "target":     r["target"] or "--",
                "details":    r["details"] or "",
                "severity":   r["severity"],
                "ip_address": r["ip_address"] or "--",
                "success":    r["success"],
            })

        return jsonify({"success": True, "count": len(logs), "logs": logs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@logs_bp.route("/api/audit-logs/stats", methods=["GET"])
def get_audit_stats():
    """Statistiques globales pour les cartes du dashboard de logs."""
    ensure_audit_table()
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                COUNT(*)                                                          AS total,
                COUNT(*) FILTER (WHERE LOWER(severity) = 'high')                 AS high,
                COUNT(*) FILTER (WHERE LOWER(severity) = 'medium')               AS medium,
                COUNT(*) FILTER (WHERE LOWER(severity) = 'info')                 AS info,
                COUNT(*) FILTER (WHERE success = FALSE)                          AS failures,
                COUNT(DISTINCT actor)                                             AS unique_actors,
                COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '1 hour')   AS last_hour,
                COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '24 hours') AS last_day
            FROM audit_logs
        """)
        row = cur.fetchone()

        # Répartition par catégorie
        cur.execute("""
            SELECT category, COUNT(*) AS cnt
            FROM audit_logs
            GROUP BY category
            ORDER BY cnt DESC
        """)
        categories = [{"name": r["category"], "count": r["cnt"]} for r in cur.fetchall()]

        return jsonify({
            "success": True,
            "stats": dict(row),
            "categories": categories,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@logs_bp.route("/api/audit-logs", methods=["POST"])
def create_audit_log():
    """
    Endpoint pour écrire manuellement un log depuis le frontend (consultations de pages).
    Body JSON: { actor, role, action, category, target, details, severity }
    """
    ensure_audit_table()
    data = request.get_json() or {}

    write_audit_log(
        action     = data.get("action", "Page consultée"),
        category   = data.get("category", "navigation"),
        target     = data.get("target"),
        details    = data.get("details"),
        severity   = data.get("severity", "Info"),
        success    = data.get("success", True),
        actor      = data.get("actor", "unknown"),
        role       = data.get("role", "unknown"),
        ip_address = request.remote_addr,
    )
    return jsonify({"success": True, "message": "Log enregistré"}), 201


@logs_bp.route("/api/audit-logs/<int:log_id>", methods=["DELETE"])
def delete_audit_log(log_id):
    """Supprime un log spécifique (admin only)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM audit_logs WHERE id = %s RETURNING id", (log_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Log introuvable"}), 404
        conn.commit()
        return jsonify({"success": True, "message": f"Log {log_id} supprimé"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@logs_bp.route("/api/audit-logs/clear", methods=["POST"])
def clear_audit_logs():
    """Vide tous les logs d'audit (admin only)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE audit_logs RESTART IDENTITY")
        conn.commit()
        return jsonify({"success": True, "message": "Tous les logs ont été supprimés"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()
