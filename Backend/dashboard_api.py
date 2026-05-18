"""
dashboard_api.py
================
Blueprint exposing GET /api/dashboard/summary.

It aggregates data from the existing Database modules so the front-end
dashboard can load everything in a single request instead of hitting
multiple routes.

Registration (add to app.py):
    from dashboard_api import dashboard_bp
    app.register_blueprint(dashboard_bp)

Adjust the imported function names below if your Database modules
expose different names (e.g. get_alerts() vs get_all_alerts()).
"""

import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

dashboard_bp = Blueprint("dashboard", __name__)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ts(ts):
    """Parse an ISO-ish timestamp string into a datetime; return datetime.min on failure."""
    if not ts:
        return datetime.min
    s = str(ts)[:19]  # trim microseconds / timezone
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.min


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@dashboard_bp.get("/api/dashboard/summary")
@jwt_required()
def dashboard_summary():
    """
    Aggregate endpoint consumed by dashboard.html.

    Returns:
    {
        success: bool,
        stats:          { total, critical, medium, low, unique_sources, rate_per_minute },
        recentAlerts:   [ { name, src, dst, severity, timestamp }, ... ]  (last 5),
        trafficStatus:  { status, color, bg },
        rulesCount:     int,
        vlanStats:      { count, lastCreated, quarantine },
        interfaceStats: { total, up, down, securePorts, hasAlert },
        lastTriggeredRule: { name, action, description } | null,
        userActivities: [ { username, action, timestamp }, ... ]
    }
    """

    # ── 1. Alerts ─────────────────────────────────────────────────────────────
    stats = {
        "total": 0, "critical": 0, "medium": 0, "low": 0,
        "unique_sources": 0, "rate_per_minute": 0,
    }
    recent_alerts = []
    traffic_status = {"status": "Normal", "color": "#22c55e", "bg": "bg-green"}

    try:
        # ⚠️  Adjust the import path / function name to match your module.
        #     Common candidates: get_all_alerts, fetch_alerts, list_alerts …
        from Database.alerts import get_all_alerts  # noqa: PLC0415

        alerts: list = get_all_alerts() or []

        stats["total"]          = len(alerts)
        stats["critical"]       = sum(1 for a in alerts if a.get("severity") == "critical")
        stats["medium"]         = sum(1 for a in alerts if a.get("severity") == "medium")
        stats["low"]            = sum(1 for a in alerts if a.get("severity") == "low")
        stats["unique_sources"] = len({a.get("src") for a in alerts if a.get("src")})

        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)
        stats["rate_per_minute"] = sum(
            1 for a in alerts if _parse_ts(a.get("timestamp")) > one_minute_ago
        )

        # Traffic status derived from critical alerts in the last 24 h
        one_day_ago  = now - timedelta(hours=24)
        critical_24h = sum(
            1 for a in alerts
            if a.get("severity") == "critical"
            and _parse_ts(a.get("timestamp")) > one_day_ago
        )
        if critical_24h == 0:
            traffic_status = {"status": "Normal",    "color": "#22c55e", "bg": "bg-green"}
        elif critical_24h <= 5:
            traffic_status = {"status": "Attention", "color": "#f59e0b", "bg": "bg-amber"}
        else:
            traffic_status = {"status": "Critique",  "color": "#ef4444", "bg": "bg-red"}

        # Most recent 5 alerts for the log section
        recent_alerts = sorted(
            alerts, key=lambda a: a.get("timestamp", ""), reverse=True
        )[:5]

    except Exception as exc:
        logger.warning("dashboard_summary – alerts error: %s", exc)

    # ── 2. Rules (IDS / Snort) ────────────────────────────────────────────────
    rules_count        = 0
    last_triggered_rule = None

    try:
        # ⚠️  Adjust to your actual function name.
        from Database.regles import get_all_regles  # noqa: PLC0415

        rules: list = get_all_regles() or []
        rules_count  = len(rules)

        # Find the most recently matched rule by comparing alert names with rule names
        if recent_alerts and rules:
            rule_by_name = {r.get("name"): r for r in rules if r.get("name")}
            for alert in recent_alerts:
                matched = rule_by_name.get(alert.get("name"))
                if matched:
                    last_triggered_rule = {
                        "name":        matched.get("name", ""),
                        "action":      matched.get("action", "--"),
                        "description": matched.get("description", ""),
                    }
                    break

    except Exception as exc:
        logger.warning("dashboard_summary – regles error: %s", exc)

    # ── 3. VLANs ──────────────────────────────────────────────────────────────
    vlan_stats = {"count": 0, "lastCreated": None, "quarantine": None}

    try:
        # ⚠️  Adjust to your actual function name.
        from Database.vlan import get_all_vlans  # noqa: PLC0415

        vlans: list = get_all_vlans() or []
        vlan_stats["count"] = len(vlans)

        if vlans:
            # Assumes the list is ordered by creation (oldest → newest).
            # If not, sort by id_vlan / id before taking the last element.
            vlan_stats["lastCreated"] = vlans[-1]
            # Quarantine VLAN: look for one named "quarantine" (case-insensitive)
            vlan_stats["quarantine"] = next(
                (v for v in vlans
                 if "quarantine" in str(v.get("nom", v.get("name", ""))).lower()),
                None,
            )

    except Exception as exc:
        logger.warning("dashboard_summary – vlan error: %s", exc)

    # ── 4. Interfaces ─────────────────────────────────────────────────────────
    interface_stats = {
        "total": 0, "up": 0, "down": 0, "securePorts": 0, "hasAlert": False,
    }

    try:
        # ⚠️  Adjust to your actual function name.
        from Database.interface import get_all_interfaces  # noqa: PLC0415

        interfaces: list = get_all_interfaces() or []
        interface_stats["total"] = len(interfaces)

        # Accept several possible field names / values for "up"
        _UP_VALUES = {"up", "actif", "active", "1", "true", True, 1}
        interface_stats["up"] = sum(
            1 for i in interfaces
            if str(i.get("status", i.get("etat", i.get("state", "")))).lower()
            in _UP_VALUES
            or i.get("status") is True
        )
        interface_stats["down"]       = interface_stats["total"] - interface_stats["up"]
        interface_stats["securePorts"] = sum(
            1 for i in interfaces
            if i.get("port_security") or i.get("securite_port")
        )
        interface_stats["hasAlert"] = stats["critical"] > 0

    except Exception as exc:
        logger.warning("dashboard_summary – interface error: %s", exc)

    # ── 5. User activities (optional – from audit logs) ───────────────────────
    user_activities: list = []

    try:
        # ⚠️  Expose a get_recent_user_activities(limit) helper in log_api.py
        #     and import it here, or replace with your own DB query.
        from log_api import get_recent_user_activities  # noqa: PLC0415

        user_activities = get_recent_user_activities(limit=10) or []

    except Exception:
        pass  # User activities are optional; silently skip if unavailable.

    # ── Response ───────────────────────────────────────────────────────────────
    return jsonify({
        "success":          True,
        "stats":            stats,
        "recentAlerts":     recent_alerts,
        "trafficStatus":    traffic_status,
        "rulesCount":       rules_count,
        "vlanStats":        vlan_stats,
        "interfaceStats":   interface_stats,
        "lastTriggeredRule": last_triggered_rule,
        "userActivities":   user_activities,
    })