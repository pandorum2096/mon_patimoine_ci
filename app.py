"""
Mon Patrimoine CI — Backend Flask
Hébergement : Render.com
Base de données : PostgreSQL (Neon / Render / Supabase)
Auth : JWT (PyJWT)
"""

import os
import json
import datetime
import functools
import bcrypt
import jwt

# Charger .env automatiquement (développement local)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback manuel si python-dotenv pas installé
    _env = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(_env):
        with open(_env) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())

# Compatibilité Windows (pg8000) + Linux/Render (psycopg2)
try:
    import psycopg2
    import psycopg2.extras
    DB_DRIVER = "psycopg2"
except ImportError:
    import pg8000.native
    DB_DRIVER = "pg8000"

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ─── Config ───────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static")
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SECRET_KEY   = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
PORT         = int(os.environ.get("PORT", 5000))
JWT_EXPIRY   = 30  # jours

# ─── Base de données ──────────────────────────────────────────────────────────
def get_conn():
    url = DATABASE_URL
    if DB_DRIVER == "psycopg2":
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url)
    else:
        # pg8000 : parse manuelle de l'URL
        import urllib.parse
        p = urllib.parse.urlparse(url)
        return pg8000.native.Connection(
            user=p.username,
            password=p.password,
            host=p.hostname,
            port=p.port or 5432,
            database=p.path.lstrip("/"),
            ssl_context=True,
        )


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           SERIAL PRIMARY KEY,
            email        TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nom          TEXT NOT NULL DEFAULT '',
            created_at   TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patrimoine_data (
            user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            data       JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Base de données initialisée")


# ─── JWT Helpers ──────────────────────────────────────────────────────────────
def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=JWT_EXPIRY),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])


def require_auth(f):
    """Décorateur : vérifie le token JWT dans Authorization: Bearer <token>"""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Token manquant"}), 401
        try:
            payload = decode_token(auth.split(" ", 1)[1])
            request.user_id = payload["sub"]
            request.user_email = payload["email"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expirée, veuillez vous reconnecter"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token invalide"}), 401
        return f(*args, **kwargs)
    return wrapper


# ─── Routes AUTH ──────────────────────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    body = request.get_json() or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    nom = (body.get("nom") or "").strip()

    if not email or not password or not nom:
        return jsonify({"error": "Email, mot de passe et prénom sont requis"}), 400
    if len(password) < 6:
        return jsonify({"error": "Le mot de passe doit faire au moins 6 caractères"}), 400
    if "@" not in email:
        return jsonify({"error": "Email invalide"}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, nom) VALUES (%s, %s, %s) RETURNING id",
            (email, pw_hash, nom)
        )
        user_id = cur.fetchone()[0]
        # Initialiser les données patrimoine
        cur.execute(
            "INSERT INTO patrimoine_data (user_id, data) VALUES (%s, %s)",
            (user_id, json.dumps({}))
        )
        conn.commit()
        cur.close()
        conn.close()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Cet email est déjà utilisé"}), 409
    except Exception as e:
        return jsonify({"error": f"Erreur serveur : {str(e)}"}), 500

    token = create_token(user_id, email)
    return jsonify({"token": token, "nom": nom, "email": email}), 201


@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json() or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email et mot de passe requis"}), 400

    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, email, password_hash, nom FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": f"Erreur serveur : {str(e)}"}), 500

    if not user:
        return jsonify({"error": "Email ou mot de passe incorrect"}), 401
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Email ou mot de passe incorrect"}), 401

    token = create_token(user["id"], user["email"])
    return jsonify({"token": token, "nom": user["nom"], "email": user["email"]}), 200


@app.route("/api/me", methods=["GET"])
@require_auth
def me():
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, email, nom, created_at FROM users WHERE id = %s", (request.user_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        return jsonify(dict(user))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Routes DONNÉES ───────────────────────────────────────────────────────────
@app.route("/api/load", methods=["GET"])
@require_auth
def load_data():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT data FROM patrimoine_data WHERE user_id = %s",
            (request.user_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return jsonify(row[0] if row else {}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/save", methods=["POST"])
@require_auth
def save_data():
    data = request.get_json()
    if data is None:
        return jsonify({"error": "Corps JSON invalide"}), 400
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO patrimoine_data (user_id, data, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
        """, (request.user_id, json.dumps(data)))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export", methods=["GET"])
@require_auth
def export_data():
    """Export JSON des données de l'utilisateur connecté."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT data, updated_at FROM patrimoine_data WHERE user_id = %s", (request.user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return jsonify({"data": row[0], "updated_at": str(row[1])} if row else {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete-account", methods=["DELETE"])
@require_auth
def delete_account():
    """Supprime le compte et toutes les données (CASCADE)."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = %s", (request.user_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Health check ─────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "app": "Mon Patrimoine CI"}), 200


# ─── Frontend ─────────────────────────────────────────────────────────────────
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    return send_from_directory(".", "index.html")


# ─── Démarrage ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=PORT, debug=debug)
