"""
audit_hooks.py
==============
Décorateurs et utilitaires à utiliser dans chaque blueprint pour enregistrer
automatiquement toutes les actions utilisateur dans audit_logs.

Usage dans un blueprint :
    from audit_hooks import audit_after

    @vlan_bp.route("/api/vlan", methods=["POST"])
    @audit_after(action="Création VLAN", category="vlan", severity="Medium")
    def create_vlan():
        ...
"""

from functools import wraps
from flask import request, g
import json


def _get_actor():
    """Tente de lire l'acteur depuis le contexte Flask."""
    # Priorité : g.current_user → header X-Actor → header Authorization → 'unknown'
    user = getattr(g, "current_user", None)
    if user:
        if hasattr(user, "username"):
            return user.username, getattr(user, "role", "unknown")
        return str(user), "unknown"

    actor_header = request.headers.get("X-Actor", "")
    if actor_header:
        return actor_header, request.headers.get("X-Role", "unknown")

    return "unknown", "unknown"


def audit_after(action, category, severity="Info", get_target=None):
    """
    Décorateur qui enregistre un log APRÈS l'exécution de la route.
    - action    : str décrivant l'action (ex: "Création VLAN")
    - category  : str catégorie (vlan, interface, regle, user, alert, navigation)
    - severity  : Info | Medium | High
    - get_target: callable(request, response_data) → str, pour extraire la cible depuis la réponse
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from logs import write_audit_log

            response = fn(*args, **kwargs)
            actor, role = _get_actor()

            # Extraire le code HTTP
            if isinstance(response, tuple):
                resp_obj, status_code = response[0], response[1]
            else:
                resp_obj, status_code = response, 200

            success = 200 <= int(status_code) < 400

            # Tenter de lire le corps JSON pour extraire la cible
            target = None
            details = None
            try:
                data = resp_obj.get_json() if hasattr(resp_obj, "get_json") else {}
                if callable(get_target) and data:
                    target = get_target(request, data)
                elif data:
                    # Chercher un champ "id" ou "name" générique
                    for key in ("nom", "name", "id_vlan", "sid", "id", "username"):
                        if key in data:
                            target = str(data[key])
                            break
                    if not target and "vlan" in data:
                        target = f"VLAN {data['vlan'].get('id_vlan', '')} – {data['vlan'].get('nom', '')}"
                    if not success and data.get("error"):
                        details = f"Erreur: {data['error']}"
            except Exception:
                pass

            write_audit_log(
                action=action,
                category=category,
                target=target or "",
                details=details,
                severity=severity if success else "High",
                success=success,
                actor=actor,
                role=role,
                ip_address=request.remote_addr,
            )
            return response
        return wrapper
    return decorator
