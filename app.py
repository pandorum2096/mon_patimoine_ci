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
import urllib.request as _urllib_req

# Charger .env automatiquement (développement local)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ENV_PATH, override=True)
    print(f"✅ .env chargé depuis : {_ENV_PATH}")
except ImportError:
    # Fallback manuel si python-dotenv pas installé
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ[_k.strip()] = _v.strip()
        print(f"✅ .env chargé (fallback manuel) depuis : {_ENV_PATH}")
    else:
        print(f"⚠️  Fichier .env introuvable : {_ENV_PATH}")

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

@app.before_request
def log_request():
    print(f"→ {request.method} {request.path}  |  Auth: {'Bearer ...' if request.headers.get('Authorization','').startswith('Bearer ') else 'none'}")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SECRET_KEY   = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
PORT         = int(os.environ.get("PORT", 5000))
JWT_EXPIRY   = 30  # jours

# ─── Vérification au démarrage ────────────────────────────────────────────────
if not DATABASE_URL:
    print("❌ ERREUR : DATABASE_URL non défini. Vérifiez votre fichier .env")
else:
    host = DATABASE_URL.split("@")[-1].split("/")[0] if "@" in DATABASE_URL else "?"
    print(f"✅ DATABASE_URL chargé — hôte : {host}")
    print(f"✅ Driver DB      : {DB_DRIVER}")
    print(f"✅ SECRET_KEY     : {SECRET_KEY[:8]}... ({len(SECRET_KEY)} chars)")

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
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),   # PyJWT >= 2.0 exige string pour "sub" (RFC 7519)
        "email": email,
        "exp": now + datetime.timedelta(days=JWT_EXPIRY),
        "iat": now,
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
            print(f"❌ require_auth: pas de Bearer token sur {request.path}")
            return jsonify({"error": "Token manquant"}), 401
        token_str = auth.split(" ", 1)[1]
        if not token_str:
            print(f"❌ require_auth: token vide sur {request.path}")
            return jsonify({"error": "Token vide"}), 401
        try:
            payload = decode_token(token_str)
            request.user_id = int(payload["sub"])   # sub est stocké en string, on reconvertit en int pour les requêtes DB
            request.user_email = payload["email"]
        except jwt.ExpiredSignatureError:
            print(f"❌ require_auth: token expiré sur {request.path}")
            return jsonify({"error": "Session expirée, veuillez vous reconnecter"}), 401
        except jwt.InvalidTokenError as e:
            print(f"❌ require_auth: InvalidTokenError sur {request.path} — {type(e).__name__}: {e}")
            print(f"   token_len={len(token_str)}, token_prefix={token_str[:20]}...")
            print(f"   secret_key_used={SECRET_KEY[:8]}... ({len(SECRET_KEY)} chars)")
            return jsonify({"error": "Token invalide"}), 401
        except Exception as e:
            print(f"❌ require_auth: ERREUR INATTENDUE sur {request.path} — {type(e).__name__}: {e}")
            return jsonify({"error": "Erreur d'authentification"}), 401
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
    except Exception as e:
        err = str(e).lower()
        if "unique" in err or "duplicate" in err:
            return jsonify({"error": "Cet email est déjà utilisé"}), 409
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
        if DB_DRIVER == "psycopg2":
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT id, email, password_hash, nom FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            user = dict(row) if row else None
        else:
            cur = conn.cursor()
            cur.execute("SELECT id, email, password_hash, nom FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            user = {"id": row[0], "email": row[1], "password_hash": row[2], "nom": row[3]} if row else None
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ /api/login DB error: {e}")
        return jsonify({"error": f"Erreur serveur : {str(e)}"}), 500

    if not user:
        return jsonify({"error": "Email ou mot de passe incorrect"}), 401
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Email ou mot de passe incorrect"}), 401

    token = create_token(user["id"], user["email"])
    print(f"✅ /api/login OK — user_id={user['id']} email={user['email']}")
    return jsonify({"token": token, "nom": user["nom"], "email": user["email"]}), 200


@app.route("/api/me", methods=["GET"])
@require_auth
def me():
    try:
        conn = get_conn()
        if DB_DRIVER == "psycopg2":
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT id, email, nom, created_at FROM users WHERE id = %s", (request.user_id,))
            row = cur.fetchone()
            result = dict(row) if row else {}
        else:
            cur = conn.cursor()
            cur.execute("SELECT id, email, nom, created_at FROM users WHERE id = %s", (request.user_id,))
            row = cur.fetchone()
            result = {"id": row[0], "email": row[1], "nom": row[2], "created_at": str(row[3])} if row else {}
        cur.close()
        conn.close()
        return jsonify(result)
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
        result = row[0] if row else {}
        print(f"✅ /api/load user={request.user_id} — {'données trouvées' if result else 'vide'}")
        return jsonify(result), 200
    except Exception as e:
        print(f"❌ /api/load user={request.user_id} — ERREUR : {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/save", methods=["POST"])
@require_auth
def save_data():
    data = request.get_json()
    if data is None:
        print(f"⚠️  /api/save user={request.user_id} — corps JSON invalide")
        return jsonify({"error": "Corps JSON invalide"}), 400
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO patrimoine_data (user_id, data, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
        """, (request.user_id, json.dumps(data, ensure_ascii=False)))
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ /api/save user={request.user_id} — OK")
        return jsonify({"ok": True}), 200
    except Exception as e:
        print(f"❌ /api/save user={request.user_id} — ERREUR : {e}")
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


# ─── IA — Config auto : Groq (production) ou Ollama (local) ──────────────────
#
#  LOCAL  (FLASK_ENV=development ou pas de GROQ_API_KEY) → Ollama localhost:11434
#  RENDER (GROQ_API_KEY définie dans les env vars)        → Groq Cloud (gratuit)
#
OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
FLASK_ENV    = os.environ.get("FLASK_ENV",    "production")

# Groq si la clé est présente (local ou prod), Ollama sinon
USE_GROQ = bool(GROQ_API_KEY)

# Modèle Groq par défaut (llama3 compatible, gratuit)
GROQ_MODEL_DEFAULT = "llama-3.3-70b-versatile"
GROQ_API_URL       = "https://api.groq.com/openai/v1/chat/completions"

print(f"🤖 Mode IA : {'GROQ CLOUD (' + GROQ_MODEL_DEFAULT + ')' if USE_GROQ else 'OLLAMA LOCAL (' + OLLAMA_URL + ')'}")


def _build_prompt(nom, revenu_m, profil_r, mois, revenus, depenses, epargne, solde, patrimoine, actif_txt, obj_txt):
    taux_ep = round(epargne / revenus * 100, 1) if revenus > 0 else 0
    return f"""Tu es un conseiller financier expert spécialisé en finances personnelles en Côte d'Ivoire (zone UEMOA, devise FCFA).
Tu donnes des conseils précis, concrets et adaptés au contexte ivoirien. Réponds en français.

PROFIL :
- Nom : {nom}
- Revenu mensuel déclaré : {revenu_m:,.0f} FCFA
- Profil de risque : {profil_r}

SITUATION DU MOIS ({mois}) :
- Revenus encaissés : {revenus:,.0f} FCFA
- Dépenses : {depenses:,.0f} FCFA
- Épargne + investissements : {epargne:,.0f} FCFA
- Taux d'épargne : {taux_ep}%
- Solde disponible : {solde:,.0f} FCFA
- Patrimoine net total : {patrimoine:,.0f} FCFA

ACTIFS DÉTENUS : {actif_txt}
OBJECTIFS EN COURS : {obj_txt}

MISSION : Donne 4 à 5 conseils financiers personnalisés, précis et actionnables basés sur cette situation réelle.
- Inclus des montants FCFA concrets et réalistes
- Mentionne des produits disponibles en CI si pertinent (Djamo Invest, NSIA AM, BRVM, Orange Money Épargne, etc.)
- Sois direct, bienveillant et motivant
- Structure ta réponse avec des titres courts (ex: "💡 Optimise ton épargne") et des points clairs
- Maximum 500 mots

Réponds uniquement en français."""


def _call_groq(prompt, model=None):
    """Appelle l'API Groq via le SDK officiel (évite les blocages Cloudflare)."""
    from groq import Groq as _Groq
    model = model or GROQ_MODEL_DEFAULT
    groq_models = {
        # Anciens noms → nouveaux modèles actifs Groq (2025-2026)
        "llama-3.3-70b-versatile": "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile": "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768":      "mixtral-8x7b-32768",
        # Anciens noms → meilleur modèle actif
        "llama3":                  "llama-3.3-70b-versatile",
        "llama3:8b":               "llama-3.3-70b-versatile",
        "llama3:70b":              "llama-3.3-70b-versatile",
        "llama3-8b-8192":          "llama-3.3-70b-versatile",
        "llama3-70b-8192":         "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant":    "llama-3.3-70b-versatile",
        "gemma2":                  "llama-3.3-70b-versatile",
        "gemma2-9b-it":            "llama-3.3-70b-versatile",
        "gemma":                   "llama-3.3-70b-versatile",
    }
    groq_model = groq_models.get(model, GROQ_MODEL_DEFAULT)
    print(f"[Groq SDK] model={groq_model} key_prefix={GROQ_API_KEY[:12]}...")

    client = _Groq(api_key=GROQ_API_KEY)
    chat   = client.chat.completions.create(
        model=groq_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=700,
    )
    return chat.choices[0].message.content.strip(), groq_model


def _call_ollama(prompt, model="llama3"):
    """Appelle Ollama en local."""
    payload = json.dumps({
        "model":   model,
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0.7, "num_predict": 700}
    }).encode("utf-8")

    req = _urllib_req.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with _urllib_req.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("response", "").strip(), model


@app.route("/api/conseil-ia", methods=["POST"])
@require_auth
def conseil_ia():
    """Conseil IA — utilise Groq en prod, Ollama en local."""
    body = request.get_json() or {}

    profile    = body.get("profile",    {})
    revenus    = body.get("revenus",    0)
    depenses   = body.get("depenses",   0)
    solde      = body.get("solde",      0)
    epargne    = body.get("epargne",    0)
    patrimoine = body.get("patrimoine", 0)
    objectifs  = body.get("objectifs",  [])
    actifs     = body.get("actifs",     [])
    mois       = body.get("mois",       "")
    model      = body.get("model",      "llama3")

    nom      = profile.get("nom",           "l'utilisateur")
    revenu_m = profile.get("revenuMensuel", 0)
    profil_r = profile.get("profilRisque",  "équilibré")

    obj_txt   = ", ".join([f"{o.get('nom','?')} ({o.get('epargne',0):,.0f}/{o.get('cible',0):,.0f} FCFA)" for o in objectifs[:4]]) or "Aucun objectif"
    actif_txt = ", ".join([f"{a.get('nom','?')} ({a.get('valeurActuelle',0):,.0f} FCFA)" for a in actifs[:5]]) or "Aucun actif"

    prompt = _build_prompt(nom, revenu_m, profil_r, mois, revenus, depenses, epargne, solde, patrimoine, actif_txt, obj_txt)

    try:
        if USE_GROQ:
            conseil, used_model = _call_groq(prompt, model)
        else:
            conseil, used_model = _call_ollama(prompt, model)

        return jsonify({"ok": True, "conseil": conseil, "model": used_model, "engine": "groq" if USE_GROQ else "ollama"}), 200

    except Exception as e:
        err = str(e)
        engine = "Groq" if USE_GROQ else "Ollama"
        if "Connection refused" in err or "111" in err:
            return jsonify({"ok": False, "error": f"{engine} inaccessible. Vérifiez la configuration."}), 503
        if "401" in err or "invalid_api_key" in err.lower():
                        return jsonify({"ok": False, "error": "Cle GROQ_API_KEY invalide. Verifiez vos variables d'environnement sur Render."}), 401
        return jsonify({"ok": False, "conseil": "", "error": f"[{engine}] {err}"}), 500


# ─── Liste des modèles disponibles ───────────────────────────────────────────────────────────────────────────────
@app.route("/api/ollama-models", methods=["GET"])
@require_auth
def ollama_models():
    if USE_GROQ:
        models = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "mixtral-8x7b-32768"]
        return jsonify({"ok": True, "models": models, "engine": "groq"}), 200
    try:
        req = _urllib_req.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with _urllib_req.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])]
        return jsonify({"ok": True, "models": models, "engine": "ollama"}), 200
    except Exception as e:
        return jsonify({"ok": False, "models": [], "error": str(e)}), 200


# ─── Health check ────────────────────────────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "engine": "groq" if USE_GROQ else "ollama"}), 200


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(_BASE_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = FLASK_ENV == "development"
    print(f"Serveur demarre sur http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
