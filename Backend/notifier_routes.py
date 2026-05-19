"""
notifier_routes.py — Blueprint Flask pour l'installation/arrêt du notifier IDS
À importer dans votre app.py principale :

    from notifier_routes import notifier_bp
    app.register_blueprint(notifier_bp)
"""

import os
import sys
import subprocess
import threading
import logging
from pathlib import Path
from flask import Blueprint, jsonify, request

log = logging.getLogger("ids-notifier-routes")

notifier_bp = Blueprint("notifier", __name__)

# ── Chemin vers p.bat et notifier.py (même dossier que ce fichier) ─────────
BASE_DIR     = Path(__file__).parent.resolve()
PBAT         = BASE_DIR / "p.bat"
NOTIFIER_PY  = BASE_DIR / "notifier.py"
CONFIG_DIR   = Path(os.getenv("APPDATA", "")) / "IDS_Notifier"

# État simple en mémoire (reset au redémarrage Flask)
_install_status = {"running": False, "done": False, "error": None, "log": []}
_status_lock    = threading.Lock()


def _run_install():
    """Lance p.bat en arrière-plan et capture la sortie."""
    global _install_status
    with _status_lock:
        _install_status = {"running": True, "done": False, "error": None, "log": []}

    try:
        if not PBAT.exists():
            raise FileNotFoundError(f"p.bat introuvable : {PBAT}")

        log.info(f"[Notifier] Lancement de {PBAT}")
        proc = subprocess.Popen(
            ["cmd.exe", "/c", str(PBAT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="cp1252",      # Encodage console Windows FR
            errors="replace",
            cwd=str(BASE_DIR),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        lines = []
        for line in proc.stdout:
            clean = line.rstrip()
            lines.append(clean)
            log.info(f"[p.bat] {clean}")
            with _status_lock:
                _install_status["log"] = lines[-50:]   # garder les 50 dernières lignes

        proc.wait(timeout=300)   # max 5 min

        with _status_lock:
            if proc.returncode == 0:
                _install_status.update({"running": False, "done": True, "error": None})
                log.info("[Notifier] Installation terminée avec succès.")
            else:
                _install_status.update({
                    "running": False,
                    "done": True,
                    "error": f"p.bat a retourné le code {proc.returncode}",
                })
                log.error(f"[Notifier] p.bat code={proc.returncode}")

    except Exception as exc:
        log.exception("[Notifier] Erreur lors de l'installation")
        with _status_lock:
            _install_status.update({"running": False, "done": True, "error": str(exc)})


# ── Routes ──────────────────────────────────────────────────────────────────

@notifier_bp.route("/api/notifier/install", methods=["POST"])
def notifier_install():
    """Lance l'installation du notifier (p.bat) en arrière-plan."""
    with _status_lock:
        if _install_status["running"]:
            return jsonify({"success": False, "message": "Installation déjà en cours."}), 409

    thread = threading.Thread(target=_run_install, daemon=True, name="notifier-install")
    thread.start()
    return jsonify({"success": True, "message": "Installation lancée en arrière-plan."})


@notifier_bp.route("/api/notifier/status", methods=["GET"])
def notifier_status():
    """Retourne l'état de l'installation et les dernières lignes de log."""
    with _status_lock:
        status = dict(_install_status)

    # Vérifier si pythonw.exe tourne (notifier actif)
    notifier_running = False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq pythonw.exe"],
            capture_output=True, text=True, timeout=5
        )
        notifier_running = "pythonw.exe" in result.stdout
    except Exception:
        pass

    return jsonify({
        "success": True,
        "install": status,
        "notifier_active": notifier_running,
    })


@notifier_bp.route("/api/notifier/stop", methods=["POST"])
def notifier_stop():
    """Arrête le notifier (pythonw.exe)."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "pythonw.exe"],
            capture_output=True, timeout=10
        )
        return jsonify({"success": True, "message": "Notifier arrêté."})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@notifier_bp.route("/api/notifier/start", methods=["POST"])
def notifier_start():
    """Démarre le notifier directement (sans réinstaller)."""
    run_vbs = BASE_DIR / "run_notifier.vbs"
    if not run_vbs.exists():
        return jsonify({
            "success": False,
            "message": "run_notifier.vbs introuvable. Lancez d'abord l'installation."
        }), 404
    try:
        subprocess.Popen(
            ["wscript.exe", str(run_vbs)],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return jsonify({"success": True, "message": "Notifier démarré."})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500
