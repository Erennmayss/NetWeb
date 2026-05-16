from flask import Blueprint, jsonify, request, send_file
from Database.db import get_db_connection
import psycopg2.extras
import re
import requests
import tarfile
import io

regles_bp = Blueprint("regles", __name__)


def preparer_source_regles():
    """
    Prépare la colonne source et classe les règles déjà existantes.

    source:
      - manual : règle ajoutée manuellement
      - file   : règle importée depuis fichier
      - snort  : règle téléchargée depuis la bibliothèque Snort
    """
    conn = get_db_connection()
    if conn is None:
        return

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE regles
                ADD COLUMN IF NOT EXISTS source VARCHAR(30) DEFAULT 'manual';
            """)

            cursor.execute("""
                UPDATE regles
                SET source = 'snort'
                WHERE
                    sid < 1000000
                    OR rule ILIKE '%ruleset community%'
                    OR rule ILIKE '%ruleset registered%'
                    OR rule ILIKE '%ruleset subscriber%'
                    OR rule ILIKE '%metadata:%ruleset%'
                    OR rule ILIKE '%Cisco Talos%'
                    OR rule ILIKE '%snort.org%';
            """)

            cursor.execute("""
                UPDATE regles
                SET source = 'manual'
                WHERE source IS NULL OR source = '';
            """)

            conn.commit()

    except Exception as e:
        print(f"❌ Erreur préparation source règles : {e}")

    finally:
        conn.close()


def afficher_db():
    """Récupère toutes les règles avec les règles Snort à la fin."""
    preparer_source_regles()

    conn = get_db_connection()
    if conn is None:
        return []

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT sid, rule, COALESCE(source, 'manual') AS source
            FROM regles
            ORDER BY
                CASE
                    WHEN COALESCE(source, 'manual') = 'snort' THEN 2
                    WHEN COALESCE(source, 'manual') = 'file' THEN 1
                    ELSE 0
                END,
                sid;
        """)
        return cur.fetchall()

    except Exception as e:
        print(f"❌ Erreur lecture règles : {e}")
        return []

    finally:
        conn.close()


def ajouter_regle(line, source="manual"):
    """Parse et insère une règle Snort en BDD."""
    preparer_source_regles()

    if not line or not line.strip():
        raise Exception("La règle ne peut pas être vide")

    parts = line.split()
    if len(parts) < 7:
        raise Exception(f"Format invalide : {len(parts)} parties trouvées, 7 attendues")

    if parts[4] != '->':
        raise Exception("Le séparateur '->' est manquant ou mal positionné")

    conn = get_db_connection()
    if conn is None:
        raise Exception("Connexion à la base de données impossible")

    try:
        action = parts[0]
        protocol = parts[1]
        src_ip = parts[2]
        src_port = parts[3]
        dst_ip = parts[5]
        dst_port = parts[6]

        msg_match = re.search(r'msg:"(.*?)"', line)
        sid_match = re.search(r'sid:(\d+)', line)

        message = msg_match.group(1) if msg_match else ""

        if not sid_match:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COALESCE(MAX(sid), 1000000) + 1 FROM regles")
                sid = cursor.fetchone()[0]
            line = f"{line.rstrip(';')} sid:{sid};"
        else:
            sid = int(sid_match.group(1))

        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO regles
                    (sid, message, protocol, src_ip, src_port, dst_ip, dst_port, action, rule, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (sid) DO UPDATE
                SET source =
                    CASE
                        WHEN EXCLUDED.source = 'snort' THEN 'snort'
                        ELSE regles.source
                    END
                """,
                (sid, message, protocol, src_ip, src_port, dst_ip, dst_port, action, line, source)
            )
            conn.commit()

    except Exception as e:
        raise Exception(f"Erreur ajout : {e}")

    finally:
        conn.close()


def modifier_regle(first_sid, line):
    """Met à jour une règle existante."""
    preparer_source_regles()

    if not line or not line.strip():
        raise Exception("La règle ne peut pas être vide")

    parts = line.split()
    if len(parts) < 7:
        raise Exception(f"Format invalide : {len(parts)} parties trouvées")

    if parts[4] != '->':
        raise Exception("Le séparateur '->' est manquant")

    conn = get_db_connection()
    if conn is None:
        raise Exception("Connexion à la base de données impossible")

    try:
        action = parts[0]
        protocol = parts[1]
        src_ip = parts[2]
        src_port = parts[3]
        dst_ip = parts[5]
        dst_port = parts[6]

        msg_match = re.search(r'msg:"(.*?)"', line)
        message = msg_match.group(1) if msg_match else ""

        if f"sid:{first_sid}" not in line:
            line = re.sub(r'sid:\d+', f'sid:{first_sid}', line)

        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM regles WHERE sid = %s", (first_sid,))
            exists = cursor.fetchone()[0] > 0

            if not exists:
                cursor.execute(
                    """
                    INSERT INTO regles
                        (sid, message, protocol, src_ip, src_port, dst_ip, dst_port, action, rule, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'manual')
                    """,
                    (first_sid, message, protocol, src_ip, src_port, dst_ip, dst_port, action, line)
                )
            else:
                cursor.execute(
                    """
                    UPDATE regles
                    SET message=%s,
                        protocol=%s,
                        src_ip=%s,
                        src_port=%s,
                        dst_ip=%s,
                        dst_port=%s,
                        action=%s,
                        rule=%s,
                        source='manual'
                    WHERE sid = %s
                    """,
                    (message, protocol, src_ip, src_port, dst_ip, dst_port, action, line, first_sid)
                )

            conn.commit()

    except Exception as e:
        raise Exception(f"Erreur modification : {e}")

    finally:
        conn.close()


def supprimer_regle(sid):
    """Supprime une règle par SID."""
    conn = get_db_connection()
    if conn is None:
        raise Exception("Connexion à la base de données impossible")

    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM regles WHERE sid = %s", (sid,))
            conn.commit()

    except Exception as e:
        raise Exception(f"Erreur suppression : {e}")

    finally:
        conn.close()


def reset_db():
    """Vide entièrement la table des règles."""
    conn = get_db_connection()
    if conn is None:
        raise Exception("Connexion à la base de données impossible")

    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE regles;")
            conn.commit()

    except Exception as e:
        raise Exception(f"Erreur reset : {e}")

    finally:
        conn.close()


@regles_bp.route("/api/regles", methods=["GET"])
def get_regles():
    """Récupère toutes les règles."""
    try:
        rows = afficher_db()
        regles = [
            {
                "sid": row["sid"],
                "rule": row["rule"],
                "source": row.get("source", "manual")
            }
            for row in rows
        ]
        return jsonify({"success": True, "count": len(regles), "rules": regles})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@regles_bp.route("/api/regles", methods=["POST"])
def add_regle():
    """Ajoute une nouvelle règle manuelle."""
    data = request.get_json()

    if not data or "rule" not in data:
        return jsonify({"success": False, "error": "La règle est requise"}), 400

    try:
        ajouter_regle(data["rule"], source="manual")
        return jsonify({"success": True, "message": "Règle ajoutée avec succès"}), 201

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@regles_bp.route("/api/regles/<int:sid>", methods=["PUT"])
def update_regle(sid):
    """Met à jour une règle existante."""
    data = request.get_json()

    if not data or "rule" not in data:
        return jsonify({"success": False, "error": "La règle est requise"}), 400

    try:
        modifier_regle(sid, data["rule"])
        return jsonify({"success": True, "message": f"Règle {sid} mise à jour"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@regles_bp.route("/api/regles/<int:sid>", methods=["DELETE"])
def delete_regle(sid):
    """Supprime une règle."""
    try:
        supprimer_regle(sid)
        return jsonify({"success": True, "message": f"Règle {sid} supprimée"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@regles_bp.route("/api/regles/reset", methods=["POST"])
def reset_regles():
    """Réinitialise toutes les règles."""
    try:
        reset_db()
        return jsonify({"success": True, "message": "Base de données des règles réinitialisée"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@regles_bp.route("/api/regles/export", methods=["GET"])
def export_regles():
    """Exporte toutes les règles en fichier .rules téléchargeable."""
    try:
        rows = afficher_db()
        content = "\n".join(row["rule"] for row in rows if row["rule"])

        buffer = io.BytesIO()
        buffer.write(content.encode("utf-8"))
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="text/plain",
            as_attachment=True,
            download_name="snort_rules.rules"
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@regles_bp.route("/api/regles/import", methods=["POST"])
def import_regles():
    """Importe des règles depuis un fichier .rules/.txt uploadé."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "Aucun fichier envoyé"}), 400

    file = request.files["file"]

    if not file.filename.endswith((".rules", ".txt")):
        return jsonify({"success": False, "error": "Format invalide. Utilisez .rules ou .txt"}), 400

    try:
        content = file.read().decode("utf-8")
        lines = [
            l.strip()
            for l in content.splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]

        added = 0
        errors = []

        for line in lines:
            try:
                ajouter_regle(line, source="file")
                added += 1
            except Exception as e:
                errors.append({"rule": line[:60] + "...", "error": str(e)})

        return jsonify({
            "success": True,
            "added": added,
            "errors": errors,
            "message": f"{added} règle(s) importée(s), {len(errors)} erreur(s)"
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@regles_bp.route("/api/regles/download-from-snort", methods=["POST"])
def download_from_snort():
    """
    Télécharge les règles officielles Snort depuis snort.org
    et les classe avec source='snort'.
    """
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "Body JSON requis"}), 400

    source = data.get("source", "community")
    oinkcode = data.get("oinkcode", "").strip()

    if source == "community":
        url = "https://www.snort.org/downloads/community/community-rules.tar.gz"

    elif source == "registered":
        if not oinkcode:
            return jsonify({
                "success": False,
                "error": "L'Oinkcode est requis pour les règles enregistrées"
            }), 400

        url = f"https://www.snort.org/rules/snortrules-snapshot-29200.tar.gz?oinkcode={oinkcode}"

    else:
        return jsonify({
            "success": False,
            "error": "Source invalide. Valeurs acceptées : 'community' ou 'registered'"
        }), 400

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; NetGuard-IDS/1.0)"
        }

        resp = requests.get(url, headers=headers, timeout=90, stream=True)

        if resp.status_code == 401:
            return jsonify({"success": False, "error": "Oinkcode invalide ou expiré (HTTP 401)"}), 401

        if resp.status_code == 403:
            return jsonify({"success": False, "error": "Accès refusé. Vérifiez votre Oinkcode (HTTP 403)"}), 403

        if resp.status_code == 404:
            return jsonify({
                "success": False,
                "error": "Fichier introuvable sur snort.org. Les règles sont peut-être temporairement indisponibles."
            }), 404

        if resp.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"Erreur HTTP {resp.status_code} depuis snort.org"
            }), 502

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            return jsonify({
                "success": False,
                "error": "snort.org a retourné une page HTML — Oinkcode probablement invalide ou session expirée"
            }), 400

        tar_bytes = io.BytesIO(resp.content)

    except requests.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error": "Timeout : snort.org met trop de temps à répondre (>90s)"
        }), 504

    except requests.exceptions.ConnectionError:
        return jsonify({
            "success": False,
            "error": "Impossible de contacter snort.org. Vérifiez la connexion réseau."
        }), 503

    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": f"Erreur réseau : {e}"}), 503

    try:
        rules_lines = []
        files_parsed = []

        with tarfile.open(fileobj=tar_bytes, mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".rules") and member.isfile():
                    files_parsed.append(member.name)
                    f = tar.extractfile(member)

                    if f:
                        content = f.read().decode("utf-8", errors="ignore")
                        for line in content.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                rules_lines.append(line)

        if not rules_lines:
            return jsonify({
                "success": False,
                "error": f"Aucune règle trouvée dans l'archive. Fichiers .rules détectés : {len(files_parsed)}"
            }), 404

    except tarfile.TarError as e:
        return jsonify({
            "success": False,
            "error": f"Impossible de lire l'archive tar.gz : {e}"
        }), 400

    added = 0
    skipped = 0
    errors = []

    for line in rules_lines:
        try:
            ajouter_regle(line, source="snort")
            added += 1

        except Exception as e:
            err_msg = str(e).lower()

            if any(kw in err_msg for kw in ["conflict", "already exists", "unique", "do nothing"]):
                skipped += 1
            else:
                if len(errors) < 20:
                    errors.append({
                        "rule": line[:80] + ("..." if len(line) > 80 else ""),
                        "error": str(e)
                    })

    preparer_source_regles()

    return jsonify({
        "success": True,
        "source": source,
        "files_parsed": len(files_parsed),
        "total_in_archive": len(rules_lines),
        "added": added,
        "skipped_duplicates": skipped,
        "errors_count": len(errors),
        "errors": errors,
        "message": (
            f"{added} règle(s) importée(s) depuis snort.org "
            f"({skipped} doublon(s) ignoré(s)"
            + (f", {len(errors)} erreur(s)" if errors else "")
            + ")"
        )
    })
