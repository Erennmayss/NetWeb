from flask import Blueprint, request, jsonify
from Database.db import get_db_connection
from utils.decorators import require_role
from utils.security import hash_password
import psycopg2
import re

# Création du Blueprint pour les utilisateurs
users_bp = Blueprint('users', __name__)

class User:
    def __init__(self, id, username, email, password, role):
        self.id = id
        self.username = username
        self.email = email
        self.password = password
        self.role = role

def validate_password(password):
    """Valide que le mot de passe respecte les règles de sécurité."""
    if len(password) < 8:
        return "Le mot de passe doit contenir au moins 8 caractères"
    if not re.search(r'[A-Z]', password):
        return "Le mot de passe doit contenir au moins une majuscule"
    if not re.search(r'[0-9]', password):
        return "Le mot de passe doit contenir au moins un chiffre"
    if not re.search(r'[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\/\\]', password):
        return "Le mot de passe doit contenir au moins un caractère spécial"
    return None  # ✅ Mot de passe valide

@users_bp.route("/users", methods=["POST"])
@require_role("ADMIN")
def create_user():
    data = request.json
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role")

    if not all([username, email, password, role]):
        return jsonify({"error": "Données incomplètes"}), 400

    # ✅ Validation mot de passe fort
    pw_error = validate_password(password)
    if pw_error:
        return jsonify({"error": pw_error}), 400

    hashed_pw = hash_password(password).decode('utf-8')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO utilisateur (username, email, password, role) VALUES (%s, %s, %s, %s) RETURNING id_user;",
            (username, email, hashed_pw, role)
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Utilisateur créé", "id": new_id}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "Cet utilisateur ou cet email existe déjà"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@users_bp.route("/users", methods=["GET"])
@require_role("ADMIN")
def get_users():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # ✅ Ajout des colonnes last_login et last_logout
        cursor.execute("""
            SELECT id_user, username, email, role, last_login, last_logout 
            FROM utilisateur
            ORDER BY id_user
        """)
        users = []
        for row in cursor.fetchall():
            users.append({
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "role": row[3],
                "last_login": row[4].isoformat() if row[4] else None,
                "last_logout": row[5].isoformat() if row[5] else None
            })
        cursor.close()
        conn.close()
        return jsonify({"users": users}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@users_bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_role("ADMIN")
def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM utilisateur WHERE id_user = %s;", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Utilisateur supprimé"}), 200

# ✅ Route pour les activités utilisateur
@users_bp.route("/api/users/activity", methods=["GET"])
@require_role("ADMIN")
def get_user_activity():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT username, last_login, last_logout 
            FROM utilisateur
            WHERE last_login IS NOT NULL OR last_logout IS NOT NULL
        """)
        
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        
        logs = []
        for user in users:
            username = user[0]
            last_login = user[1]
            last_logout = user[2]
            
            if last_login:
                logs.append({
                    "username": username,
                    "action": "login",
                    "timestamp": last_login.isoformat() if last_login else None
                })
            
            if last_logout:
                logs.append({
                    "username": username,
                    "action": "logout",
                    "timestamp": last_logout.isoformat() if last_logout else None
                })
        
        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        logs = logs[:10]
        
        return jsonify({"success": True, "logs": logs}), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500