"""
Mon Patrimoine CI — Backend Flask
"""
import os, json, datetime, functools, time as _time
import bcrypt, jwt

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ENV_PATH, override=True)
    print(f"\u2705 .env charge depuis : {_ENV_PATH}")
except ImportError:
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ[_k.strip()] = _v.strip()

try:
    import psycopg2, psycopg2.extras
    DB_DRIVER = "psycopg2"
except ImportError:
    import pg8000.native
    DB_DRIVER = "pg8000"

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SECRET_KEY   = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
PORT         = int(os.environ.get("PORT", 5000))
JWT_EXPIRY   = 30

if DATABASE_URL:
    host = DATABASE_URL.split("@")[-1].split("/")[0] if "@" in DATABASE_URL else "?"
    print(f"\u2705 DATABASE_URL : {host} | Driver: {DB_DRIVER} | Key: {SECRET_KEY[:8]}...")
else:
    print("\u274c DATABASE_URL non defini")

# ── Cache simple ──────────────────────────────────────────────────────────────
_cache = {}
def _cache_get(key, ttl=300):
    if key in _cache:
        data, ts = _cache[key]
        if _time.time() - ts < ttl:
            return data
    return None
def _cache_set(key, data):
    _cache[key] = (data, _time.time())

# ── DB ────────────────────────────────────────────────────────────────────────
def get_conn():
    url = DATABASE_URL
    if DB_DRIVER == "psycopg2":
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url)
    else:
        import urllib.parse as _up
        p = _up.urlparse(url)
        return pg8000.native.Connection(user=p.username, password=p.password,
            host=p.hostname, port=p.port or 5432, database=p.path.lstrip("/"), ssl_context=True)

def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        nom TEXT NOT NULL DEFAULT \'\', is_admin BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW(), last_login TIMESTAMP)""")
    for col, defn in [("is_admin","BOOLEAN NOT NULL DEFAULT FALSE"),("last_login","TIMESTAMP")]:
        try: cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {defn}")
        except: pass
    cur.execute("""CREATE TABLE IF NOT EXISTS patrimoine_data (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        data JSONB NOT NULL DEFAULT \'{}\', updated_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS wallet_addresses (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        network TEXT NOT NULL,
        address TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT \'\',
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(user_id, network, address))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS site_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("INSERT INTO site_settings (key, value) VALUES ('hidden_tabs', '[]') ON CONFLICT (key) DO NOTHING")
    conn.commit(); cur.close(); conn.close()
    print("\u2705 Base de donnees initialisee")

with app.app_context():
    try: init_db()
    except Exception as _e: print(f"\u26a0 init_db echoue: {_e}")

# ── JWT ───────────────────────────────────────────────────────────────────────
def create_token(user_id, email, is_admin=False):
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {"sub": str(user_id), "email": email, "is_admin": is_admin,
               "exp": now + datetime.timedelta(days=JWT_EXPIRY), "iat": now}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_token(token):
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

def require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Token manquant"}), 401
        token_str = auth.split(" ", 1)[1]
        try:
            payload = decode_token(token_str)
            request.user_id    = int(payload["sub"])
            request.user_email = payload["email"]
            request.is_admin   = bool(payload.get("is_admin", False))
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expiree"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token invalide"}), 401
        except Exception as e:
            return jsonify({"error": str(e)}), 401
        return f(*args, **kwargs)
    return wrapper

def require_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not getattr(request, "is_admin", False):
            return jsonify({"error": "Acces refuse - droits admin requis"}), 403
        return f(*args, **kwargs)
    return wrapper

# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Route introuvable"}), 404
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Erreur serveur", "detail": str(e)}), 500

@app.before_request
def log_req():
    print(f"-> {request.method} {request.path}")

# ── Frontend ──────────────────────────────────────────────────────────────────
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    base = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(base, path) if path else None
    if path and target and os.path.isfile(target):
        return send_from_directory(base, path)
    return send_from_directory(base, "index.html")

# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    body = request.get_json() or {}
    email = (body.get("email","")).strip().lower()
    password = body.get("password","")
    nom = (body.get("nom","")).strip()
    if not email or not password:
        return jsonify({"error": "Email et mot de passe requis"}), 400
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("INSERT INTO users (email,password_hash,nom) VALUES (%s,%s,%s) RETURNING id", (email,pw_hash,nom))
        uid = cur.fetchone()[0]; conn.commit()
        token = create_token(uid, email, False)
        return jsonify({"token": token, "email": email, "nom": nom}), 201
    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({"error": "Email deja utilise"}), 409
        return jsonify({"error": str(e)}), 500

@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json() or {}
    email = (body.get("email","")).strip().lower()
    password = body.get("password","")
    if not email or not password:
        return jsonify({"error": "Email et mot de passe requis"}), 400
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT id,email,password_hash,nom,is_admin FROM users WHERE email=%s", (email,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Email ou mot de passe incorrect"}), 401
        uid, em, pw_hash, nom, is_admin = row
        if not bcrypt.checkpw(password.encode(), pw_hash.encode()):
            return jsonify({"error": "Email ou mot de passe incorrect"}), 401
        cur.execute("UPDATE users SET last_login=NOW() WHERE id=%s", (uid,))
        conn.commit()
        token = create_token(uid, em, bool(is_admin))
        return jsonify({"token": token, "email": em, "nom": nom, "is_admin": bool(is_admin)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/me", methods=["GET"])
@require_auth
def me():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT email,nom,is_admin FROM users WHERE id=%s", (request.user_id,))
        row = cur.fetchone()
        if not row: return jsonify({"error": "Utilisateur introuvable"}), 404
        return jsonify({"email": row[0], "nom": row[1], "is_admin": bool(row[2])}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/load", methods=["GET"])
@require_auth
def load_data():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT data FROM patrimoine_data WHERE user_id=%s", (request.user_id,))
        row = cur.fetchone()
        if not row: return jsonify({}), 200
        data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/save", methods=["POST"])
@require_auth
def save_data():
    body = request.get_json() or {}
    try:
        conn = get_conn(); cur = conn.cursor()
        data_str = json.dumps(body)
        cur.execute("""INSERT INTO patrimoine_data (user_id,data,updated_at) VALUES (%s,%s::jsonb,NOW())
            ON CONFLICT (user_id) DO UPDATE SET data=%s::jsonb, updated_at=NOW()""",
            (request.user_id, data_str, data_str))
        conn.commit()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/delete-account", methods=["DELETE"])
@require_auth
def delete_account():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM patrimoine_data WHERE user_id=%s", (request.user_id,))
        cur.execute("DELETE FROM users WHERE id=%s", (request.user_id,))
        conn.commit()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/change-password", methods=["POST"])
@require_auth
def change_password():
    body = request.get_json() or {}
    old_pw = body.get("oldPassword","")
    new_pw = body.get("newPassword","")
    if not old_pw or not new_pw:
        return jsonify({"error": "Champs requis"}), 400
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE id=%s", (request.user_id,))
        row = cur.fetchone()
        if not row or not bcrypt.checkpw(old_pw.encode(), row[0].encode()):
            return jsonify({"error": "Mot de passe actuel incorrect"}), 401
        new_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, request.user_id))
        conn.commit()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/update-profile", methods=["POST"])
@require_auth
def update_profile():
    body = request.get_json() or {}
    nom = (body.get("nom","")).strip()
    try:
        conn = get_conn(); cur = conn.cursor()
        if nom: cur.execute("UPDATE users SET nom=%s WHERE id=%s", (nom, request.user_id))
        conn.commit()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/export", methods=["GET"])
@require_auth
def export_data():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT data FROM patrimoine_data WHERE user_id=%s", (request.user_id,))
        row = cur.fetchone()
        data = row[0] if row and isinstance(row[0],dict) else (json.loads(row[0]) if row else {})
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/conseil-ia", methods=["POST"])
@require_auth
def conseil_ia():
    body = request.get_json() or {}

    # Support ancien format (champ "question" direct) ET nouveau format (données structurées)
    question = body.get("question", "")
    if not question:
        # Construire le prompt depuis les données structurées envoyées par le frontend
        profil     = body.get("profile", {})
        revenus    = body.get("revenus", 0)
        depenses   = body.get("depenses", 0)
        solde      = body.get("solde", 0)
        epargne    = body.get("epargne", 0)
        patrimoine = body.get("patrimoine", 0)
        objectifs  = body.get("objectifs", [])
        actifs     = body.get("actifs", [])
        mois       = body.get("mois", "")
        nom        = profil.get("nom", "l'utilisateur")
        revenu_m   = profil.get("revenuMensuel", 0)
        profil_r   = profil.get("profilRisque", "équilibré")
        taux_ep    = round(epargne / revenus * 100) if revenus > 0 else 0
        ratio_dep  = round(depenses / revenus * 100) if revenus > 0 else 0
        obj_txt    = "\n".join([f"  • {o.get('nom','')} : {o.get('epargne',0):,} / {o.get('cible',0):,} FCFA ({round(o.get('epargne',0)/o.get('cible',1)*100)}%)" for o in objectifs[:4]]) or "  Aucun objectif défini"
        actif_txt  = "\n".join([f"  • {a.get('nom','')} ({a.get('type','')}) : {a.get('valeur',0):,} FCFA" for a in actifs[:5]]) or "  Aucun actif enregistré"

        system_prompt = """Tu es Marie-Claire Koné, conseillère en gestion de patrimoine senior basée à Abidjan, avec 15 ans d'expérience auprès de particuliers et familles en Côte d'Ivoire.

Ton style :
- Tu rédiges des lettres de conseil structurées, professionnelles et chaleureuses
- Tu respectes EXACTEMENT le format demandé dans le message utilisateur (introduction, conseils titrés avec emoji, résumé numéroté, clôture, signature)
- Tu utilises toujours les données réelles du client (montants FCFA exacts, noms des actifs, objectifs)
- Tu connais parfaitement l'écosystème financier ivoirien : Djamo Invest, Wave, Orange Money Épargne, NSIA AM, Coris Money, BRVM, SGBCI, SIB, BOA CI
- Tu ne dévies jamais du format — pas de markdown superflu, pas de listes hors structure
- Réponds toujours uniquement en français"""

        question = f"""Tu dois rédiger un conseil financier personnalisé pour {nom}. Voici ses données :

PROFIL :
- Nom complet : {nom}
- Revenu mensuel de référence : {revenu_m:,} FCFA
- Profil investisseur : {profil_r}

BILAN DU MOIS {mois} :
- Revenus encaissés : {revenus:,} FCFA
- Dépenses : {depenses:,} FCFA ({ratio_dep}% des revenus)
- Épargne & investissements : {epargne:,} FCFA (taux d'épargne : {taux_ep}%)
- Solde disponible en fin de mois : {solde:,} FCFA
- Patrimoine net total : {patrimoine:,} FCFA

ACTIFS DÉTENUS :
{actif_txt}

OBJECTIFS EN COURS :
{obj_txt}

---
Rédige la réponse EXACTEMENT dans ce format (respecte la structure à la lettre) :

Bonjour M./Mme. [Nom complet du client],

[1 à 2 phrases d'introduction chaleureuse qui reconnaissent sa situation du mois — félicite ce qui est positif, mentionne ce qui mérite attention.]

[Emoji] [Titre du conseil 1]
[Explication du conseil avec des chiffres FCFA concrets tirés de sa situation réelle. Sois précis et pratique.]

[Emoji] [Titre du conseil 2]
[Explication du conseil avec des chiffres FCFA concrets. Mentionne un produit CI réel si pertinent (Djamo Invest, NSIA AM, BRVM, Orange Money Épargne, Wave, Coris…).]

[Emoji] [Titre du conseil 3]
[Explication du conseil avec des chiffres FCFA concrets.]

[Emoji] [Titre du conseil 4]
[Explication du conseil avec des chiffres FCFA concrets.]

[Optionnel : Emoji] [Titre du conseil 5 si pertinent]
[Explication.]

En résumé, je vous conseille :
1. [Action concrète 1]
2. [Action concrète 2]
3. [Action concrète 3]
4. [Action concrète 4]
5. [Action concrète 5 si applicable]

[Phrase de clôture chaleureuse qui mentionne le nom du client et l'invite à poser des questions.]

Cordialement,
Marie-Claire Koné
Conseillère en Gestion de Patrimoine

---
Règles importantes :
- Utilise "M." ou "Mme." selon le contexte (par défaut "M." si prénom masculin)
- Chaque conseil doit avoir un titre court avec emoji ET un paragraphe de 2-4 lignes
- Cite des montants FCFA réels tirés des données du client
- Mentionne les actifs ou objectifs du client par leur nom exact
- Réponds uniquement en français
- Maximum 700 mots"""

    if not question:
        return jsonify({"error": "Question requise"}), 400

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        # Fallback Ollama local si pas de clé Groq
        model = body.get("model", "llama3")
        try:
            import requests as _req
            r = _req.post("http://ollama:11434/api/generate",
                headers={"Content-Type": "application/json"},
                json={"model": model, "prompt": question, "stream": False, "options": {"temperature": 0.7, "num_predict": 700}},
                timeout=120)
            d = r.json()
            return jsonify({"ok": True, "conseil": d.get("response", "Réponse vide.")}), 200
        except Exception as e:
            return jsonify({"ok": False, "error": f"Ollama inaccessible: {str(e)}. Configurez GROQ_API_KEY dans .env ou démarrez Ollama."}), 200

    try:
        import requests as _req
        r = _req.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": [
                {"role": "system", "content": system_prompt if 'system_prompt' in dir() else "Tu es Marie-Claire Koné, conseillère en gestion de patrimoine senior à Abidjan. Tu parles en français, avec chaleur et précision, comme une vraie conseillère humaine. Tu connais bien l'écosystème financier ivoirien (BRVM, NSIA AM, Djamo, Wave, Orange Money, FCFA/UEMOA)."},
                {"role": "user", "content": question}], "max_tokens": 900, "temperature": 0.75}, timeout=30)
        data = r.json()
        conseil = data["choices"][0]["message"]["content"]
        return jsonify({"ok": True, "conseil": conseil}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": f"Erreur IA: {str(e)}"}), 200


# ── Listes entreprises par indice ─────────────────────────────────────────────
_INDEX_STOCKS = {
    "^GSPC":[("AAPL","Apple"),("MSFT","Microsoft"),("NVDA","NVIDIA"),("AMZN","Amazon"),
        ("META","Meta"),("GOOGL","Alphabet A"),("GOOG","Alphabet C"),("BRK-B","Berkshire"),
        ("TSLA","Tesla"),("JPM","JPMorgan"),("LLY","Eli Lilly"),("V","Visa"),
        ("UNH","UnitedHealth"),("XOM","ExxonMobil"),("AVGO","Broadcom"),("COST","Costco"),
        ("MA","Mastercard"),("HD","Home Depot"),("JNJ","Johnson & Johnson"),("PG","P&G"),
        ("MRK","Merck"),("ABBV","AbbVie"),("CVX","Chevron"),("CRM","Salesforce"),
        ("BAC","Bank of America"),("WMT","Walmart"),("NFLX","Netflix"),("KO","Coca-Cola"),
        ("AMD","AMD"),("ORCL","Oracle"),("PEP","PepsiCo"),("TMO","Thermo Fisher"),
        ("CSCO","Cisco"),("ACN","Accenture"),("ABT","Abbott"),("MCD","McDonald's"),
        ("ADBE","Adobe"),("VZ","Verizon"),("ISRG","Intuitive Surgical"),("CMCSA","Comcast"),
        ("NEE","NextEra Energy"),("RTX","RTX Corp"),("AMGN","Amgen"),("QCOM","Qualcomm"),
        ("GS","Goldman Sachs"),("IBM","IBM"),("HON","Honeywell"),("T","AT&T"),
        ("MS","Morgan Stanley"),("CAT","Caterpillar"),("LOW","Lowes"),("BLK","BlackRock"),
        ("DE","John Deere"),("VRTX","Vertex Pharma"),("PLD","Prologis"),("ADI","Analog Devices"),
        ("REGN","Regeneron"),("CI","Cigna"),("GILD","Gilead"),("TJX","TJX Companies"),
        ("BA","Boeing"),("MU","Micron"),("MMC","Marsh McLennan"),("BSX","Boston Scientific"),
        ("C","Citigroup"),("WFC","Wells Fargo"),("USB","US Bancorp"),("COF","Capital One"),
        ("ADP","ADP"),("ECL","Ecolab"),("APH","Amphenol"),("ITW","Illinois Tool"),
        ("NOW","ServiceNow"),("LRCX","Lam Research"),("ETN","Eaton"),("ZTS","Zoetis"),
        ("KLAC","KLA Corp"),("SNPS","Synopsys"),("CDNS","Cadence"),("PNC","PNC Financial"),
        ("EMR","Emerson"),("AON","Aon"),("ICE","ICE"),("CME","CME Group"),
        ("MCO","Moodys"),("SPGI","S&P Global"),("SO","Southern Co"),("DUK","Duke Energy"),
        ("TGT","Target"),("SBUX","Starbucks"),("PM","Philip Morris"),("MO","Altria"),
        ("CVS","CVS Health"),("SYK","Stryker"),("MDT","Medtronic"),("AMAT","Applied Materials"),
        ("FCX","Freeport McMoRan"),("PXD","Pioneer Natural"),("OXY","Occidental"),
        ("CARR","Carrier Global"),("OTIS","Otis Worldwide"),("PWR","Quanta Services"),
        ("PAYX","Paychex"),("IDXX","IDEXX Labs"),("FAST","Fastenal"),("ROST","Ross Stores"),
    ],
    "^FCHI":[("MC.PA","LVMH"),("TTE.PA","TotalEnergies"),("SAN.PA","Sanofi"),
        ("AIR.PA","Airbus"),("OR.PA","L'Oreal"),("BNP.PA","BNP Paribas"),
        ("DG.PA","Vinci"),("SU.PA","Schneider Electric"),("AI.PA","Air Liquide"),
        ("KER.PA","Kering"),("ACA.PA","Credit Agricole"),("GLE.PA","Societe Generale"),
        ("CAP.PA","Capgemini"),("DSY.PA","Dassault Systemes"),("SAF.PA","Safran"),
        ("RI.PA","Pernod Ricard"),("STM.PA","STMicroelectronics"),("HO.PA","Thales"),
        ("EN.PA","Bouygues"),("VIE.PA","Veolia"),("PUB.PA","Publicis"),
        ("SGO.PA","Saint-Gobain"),("RNO.PA","Renault"),("ORA.PA","Orange"),
        ("LOB.PA","Legrand"),("CA.PA","Carrefour"),("RMS.PA","Hermes"),
        ("SW.PA","Sodexo"),("ML.PA","Michelin"),("AF.PA","Air France-KLM"),
        ("ERF.PA","Eurofins"),("FGR.PA","Eiffage"),("URW.PA","Unibail-Rodamco"),
        ("WLN.PA","Worldline"),("EDF.PA","EDF"),("CS.PA","AXA"),
        ("BN.PA","Danone"),("PP.PA","Bureau Veritas"),("TEP.PA","Teleperformance"),
        ("MT.AS","ArcelorMittal"),
    ],
    "^DJI":[("AAPL","Apple"),("MSFT","Microsoft"),("UNH","UnitedHealth"),("GS","Goldman Sachs"),
        ("HD","Home Depot"),("MCD","McDonald's"),("CAT","Caterpillar"),("BA","Boeing"),
        ("AMGN","Amgen"),("V","Visa"),("JPM","JPMorgan"),("IBM","IBM"),
        ("TRV","Travelers"),("AXP","American Express"),("CVX","Chevron"),
        ("JNJ","Johnson & Johnson"),("PG","Procter & Gamble"),("MRK","Merck"),
        ("KO","Coca-Cola"),("DIS","Disney"),("NKE","Nike"),("WMT","Walmart"),
        ("MMM","3M"),("HON","Honeywell"),("VZ","Verizon"),("CSCO","Cisco"),
        ("SHW","Sherwin-Williams"),("CRM","Salesforce"),("DOW","Dow Inc"),("INTC","Intel"),
    ],
    "^IXIC":[("AAPL","Apple"),("MSFT","Microsoft"),("NVDA","NVIDIA"),("AMZN","Amazon"),
        ("META","Meta"),("GOOGL","Alphabet"),("TSLA","Tesla"),("AVGO","Broadcom"),
        ("COST","Costco"),("ASML","ASML"),("ADBE","Adobe"),("NFLX","Netflix"),
        ("AMD","AMD"),("QCOM","Qualcomm"),("INTC","Intel"),("INTU","Intuit"),
        ("CSCO","Cisco"),("TXN","Texas Instruments"),("AMGN","Amgen"),("BKNG","Booking"),
        ("ISRG","Intuitive Surgical"),("NOW","ServiceNow"),("AMAT","Applied Materials"),
        ("MU","Micron"),("LRCX","Lam Research"),("ADI","Analog Devices"),("REGN","Regeneron"),
        ("VRTX","Vertex Pharma"),("KLAC","KLA Corp"),("SNPS","Synopsys"),("CDNS","Cadence"),
        ("MRVL","Marvell"),("FTNT","Fortinet"),("PANW","Palo Alto"),("CRWD","CrowdStrike"),
        ("ABNB","Airbnb"),("MELI","MercadoLibre"),("WDAY","Workday"),("TEAM","Atlassian"),
        ("DDOG","Datadog"),("MNST","Monster Beverage"),("ODFL","Old Dominion"),
        ("CTAS","Cintas"),("FAST","Fastenal"),("ROST","Ross Stores"),("EXC","Exelon"),
        ("ZS","Zscaler"),("OKTA","Okta"),("SPLK","Splunk"),("PCAR","PACCAR"),
    ],
    "^FTSE":[("SHEL.L","Shell"),("AZN.L","AstraZeneca"),("HSBA.L","HSBC"),
        ("ULVR.L","Unilever"),("BP.L","BP"),("GSK.L","GSK"),("RIO.L","Rio Tinto"),
        ("DGE.L","Diageo"),("REL.L","RELX"),("BA.L","BAE Systems"),
        ("NG.L","National Grid"),("LSEG.L","London Stock Exchange"),
        ("CPG.L","Compass Group"),("SGE.L","Sage Group"),("WPP.L","WPP"),
        ("EXPN.L","Experian"),("GLEN.L","Glencore"),("AAL.L","Anglo American"),
        ("PRU.L","Prudential"),("BATS.L","British American Tobacco"),
        ("LLOY.L","Lloyds Banking"),("NWG.L","NatWest"),("BARC.L","Barclays"),
        ("VOD.L","Vodafone"),("BT-A.L","BT Group"),("IHG.L","IHG Hotels"),
        ("IAG.L","IAG"),("INF.L","Informa"),("RKT.L","Reckitt"),
        ("CNA.L","Centrica"),("SSE.L","SSE"),("SVT.L","Severn Trent"),
        ("UU.L","United Utilities"),("MNDI.L","Mondi"),("IMB.L","Imperial Brands"),
        ("FERG.L","Ferguson"),("RTO.L","Rentokil"),("OCDO.L","Ocado"),
        ("JD.L","JD Sports"),("PSH.L","Pershing Square"),("III.L","3i Group"),
        ("BDEV.L","Barratt"),("TW.L","Taylor Wimpey"),("SMDS.L","DS Smith"),
        ("HIK.L","Hikma"),("DCC.L","DCC"),("SBRY.L","Sainsbury"),("TSCO.L","Tesco"),
    ],
    "^N225":[("7203.T","Toyota"),("6758.T","Sony"),("9984.T","SoftBank Group"),
        ("9432.T","NTT"),("6861.T","Keyence"),("6902.T","Denso"),
        ("8306.T","Mitsubishi UFJ"),("4063.T","Shin-Etsu Chem"),
        ("6954.T","Fanuc"),("7974.T","Nintendo"),("8035.T","Tokyo Electron"),
        ("4661.T","Oriental Land"),("9983.T","Fast Retailing"),("6367.T","Daikin"),
        ("7267.T","Honda"),("7751.T","Canon"),("6501.T","Hitachi"),
        ("6503.T","Mitsubishi Electric"),("5108.T","Bridgestone"),
        ("8058.T","Mitsubishi Corp"),("8031.T","Mitsui & Co"),("8001.T","Itochu"),
        ("9022.T","Central Japan Railway"),("4502.T","Takeda Pharma"),
        ("4568.T","Daiichi Sankyo"),("6594.T","Nidec"),("7733.T","Olympus"),
        ("2914.T","Japan Tobacco"),("3382.T","Seven & I"),("9433.T","KDDI"),
        ("9434.T","SoftBank Corp"),("6645.T","Omron"),("7011.T","Mitsubishi Heavy"),
        ("6301.T","Komatsu"),("5401.T","Nippon Steel"),("8267.T","AEON"),
        ("4755.T","Rakuten"),("7符203.T","Toyota 2"),("4519.T","Chugai Pharma"),("8053.T","Sumitomo"),
    ],
}

def _get_devise(t):
    if t.endswith(".L"): return "GBP"
    if t.endswith(".T"): return "JPY"
    if t.endswith(".PA") or t.endswith(".AS"): return "EUR"
    return "USD"

def _fetch_price(ticker, headers, req):
    try:
        r = req.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d",
                    timeout=5, headers=headers)
        meta = r.json()["chart"]["result"][0]["meta"]
        prix = meta.get("regularMarketPrice") or meta.get("previousClose", 0)
        prev = meta.get("previousClose") or prix
        return round(prix,2), round(((prix-prev)/prev*100) if prev else 0,2), round(prev,2)
    except:
        return 0, 0, 0

# ── Routes Marchés ────────────────────────────────────────────────────────────
@app.route("/api/marches/crypto", methods=["GET"])
@require_auth
def marches_crypto():
    import requests as _req
    cached = _cache_get("crypto", 120)
    if cached: return jsonify(cached), 200

    _CRYPTO_STATIC = [
        {"id":"bitcoin","symbol":"BTC","nom":"Bitcoin","prix":67000,"variation_24h":1.2,"variation_7j":3.5,"market_cap":1300000000000,"volume_24h":35000000000,"image":"","high_24h":68000,"low_24h":66000,"sparkline":[]},
        {"id":"ethereum","symbol":"ETH","nom":"Ethereum","prix":3500,"variation_24h":-0.8,"variation_7j":2.1,"market_cap":420000000000,"volume_24h":18000000000,"image":"","high_24h":3600,"low_24h":3400,"sparkline":[]},
        {"id":"tether","symbol":"USDT","nom":"Tether","prix":1.0,"variation_24h":0.0,"variation_7j":0.0,"market_cap":110000000000,"volume_24h":80000000000,"image":"","high_24h":1.0,"low_24h":1.0,"sparkline":[]},
        {"id":"binancecoin","symbol":"BNB","nom":"BNB","prix":580,"variation_24h":0.5,"variation_7j":1.8,"market_cap":85000000000,"volume_24h":2000000000,"image":"","high_24h":590,"low_24h":570,"sparkline":[]},
        {"id":"solana","symbol":"SOL","nom":"Solana","prix":175,"variation_24h":2.1,"variation_7j":5.3,"market_cap":80000000000,"volume_24h":5000000000,"image":"","high_24h":180,"low_24h":170,"sparkline":[]},
        {"id":"ripple","symbol":"XRP","nom":"XRP","prix":0.52,"variation_24h":-0.3,"variation_7j":1.0,"market_cap":28000000000,"volume_24h":1500000000,"image":"","high_24h":0.54,"low_24h":0.50,"sparkline":[]},
        {"id":"usd-coin","symbol":"USDC","nom":"USD Coin","prix":1.0,"variation_24h":0.0,"variation_7j":0.0,"market_cap":32000000000,"volume_24h":6000000000,"image":"","high_24h":1.0,"low_24h":1.0,"sparkline":[]},
        {"id":"cardano","symbol":"ADA","nom":"Cardano","prix":0.45,"variation_24h":0.9,"variation_7j":2.3,"market_cap":16000000000,"volume_24h":500000000,"image":"","high_24h":0.46,"low_24h":0.44,"sparkline":[]},
        {"id":"avalanche-2","symbol":"AVAX","nom":"Avalanche","prix":35,"variation_24h":1.5,"variation_7j":4.0,"market_cap":14000000000,"volume_24h":600000000,"image":"","high_24h":36,"low_24h":34,"sparkline":[]},
        {"id":"dogecoin","symbol":"DOGE","nom":"Dogecoin","prix":0.16,"variation_24h":0.7,"variation_7j":1.2,"market_cap":23000000000,"volume_24h":800000000,"image":"","high_24h":0.17,"low_24h":0.15,"sparkline":[]},
    ]

    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    cg_key = os.environ.get("COINGECKO_API_KEY", "")
    if cg_key:
        headers["x-cg-demo-api-key"] = cg_key

    # sparkline=false : le paramètre sparkline=true est réservé aux plans payants sur serveur distant
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20&page=1&sparkline=false&price_change_percentage=24h,7d"
    try:
        r = _req.get(url, timeout=10, headers=headers)
        if r.status_code == 429:
            print("CoinGecko rate limit (429) — fallback statique")
            _cache_set("crypto", _CRYPTO_STATIC)
            return jsonify(_CRYPTO_STATIC), 200
        if r.status_code == 403:
            print("CoinGecko acces refuse (403) — fallback statique")
            _cache_set("crypto", _CRYPTO_STATIC)
            return jsonify(_CRYPTO_STATIC), 200
        if r.status_code != 200:
            print(f"CoinGecko status {r.status_code} — fallback statique")
            _cache_set("crypto", _CRYPTO_STATIC)
            return jsonify(_CRYPTO_STATIC), 200
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            _cache_set("crypto", _CRYPTO_STATIC)
            return jsonify(_CRYPTO_STATIC), 200
        result = [{"id":c["id"],"symbol":c["symbol"].upper(),"nom":c["name"],
            "prix":c["current_price"],"variation_24h":round(c.get("price_change_percentage_24h") or 0,2),
            "variation_7j":round(c.get("price_change_percentage_7d_in_currency") or 0,2),
            "market_cap":c.get("market_cap",0),"volume_24h":c.get("total_volume",0),
            "image":c.get("image",""),"high_24h":c.get("high_24h",0),"low_24h":c.get("low_24h",0),
            "sparkline":[]}
            for c in data]
        _cache_set("crypto", result)
        return jsonify(result), 200
    except Exception as e:
        print(f"CoinGecko exception: {e} — fallback statique")
        _cache_set("crypto", _CRYPTO_STATIC)
        return jsonify(_CRYPTO_STATIC), 200

@app.route("/api/marches/crypto/<coin_id>", methods=["GET"])
@require_auth
def marches_crypto_detail(coin_id):
    import requests as _req, time as _t
    days = request.args.get("days","30")
    ck = f"crypto_detail_{coin_id}_{days}"
    cached = _cache_get(ck, 180)
    if cached: return jsonify(cached), 200
    try:
        hdrs = {"Accept":"application/json","User-Agent":"Mozilla/5.0"}
        r1 = _req.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false", timeout=12, headers=hdrs)
        if r1.status_code == 429:
            return jsonify({"error":"Limite API CoinGecko - reessayez dans 60s","rate_limit":True}), 429
        detail = r1.json()
        if "error" in detail: return jsonify({"error": detail["error"]}), 502
        _t.sleep(0.5)
        range_map={"7":"5d","30":"1mo","90":"3mo","365":"1y"}
        r2 = _req.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}&interval={'hourly' if days=='7' else 'daily'}", timeout=15, headers=hdrs)
        chart = r2.json() if r2.status_code==200 else {}
        def sample(lst,n=120):
            if not lst or len(lst)<=n: return lst
            step=max(1,len(lst)//n); return lst[::step][-n:]
        md = detail.get("market_data",{})
        result = {"id":coin_id,"nom":detail.get("name",""),"symbol":detail.get("symbol","").upper(),
            "image":(detail.get("image") or {}).get("large",""),
            "description":((detail.get("description") or {}).get("fr") or (detail.get("description") or {}).get("en",""))[:600],
            "rang":detail.get("market_cap_rank",0),
            "prix":md.get("current_price",{}).get("usd",0),
            "prix_eur":md.get("current_price",{}).get("eur",0),
            "market_cap":md.get("market_cap",{}).get("usd",0),
            "volume_24h":md.get("total_volume",{}).get("usd",0),
            "high_24h":md.get("high_24h",{}).get("usd",0),
            "low_24h":md.get("low_24h",{}).get("usd",0),
            "variation_24h":round(md.get("price_change_percentage_24h") or 0,2),
            "variation_7j":round(md.get("price_change_percentage_7d") or 0,2),
            "variation_30j":round(md.get("price_change_percentage_30d") or 0,2),
            "variation_1an":round(md.get("price_change_percentage_1y") or 0,2),
            "supply_circul":md.get("circulating_supply",0),
            "ath":md.get("ath",{}).get("usd",0),
            "ath_date":(md.get("ath_date") or {}).get("usd","")[:10],
            "chart_prices":[[p[0],round(p[1],6)] for p in sample(chart.get("prices") or [])],
            "chart_volumes":[[v[0],round(v[1],0)] for v in sample(chart.get("total_volumes") or [],60)],
            "website":((detail.get("links") or {}).get("homepage") or [""])[0],
            "categories":(detail.get("categories") or [])[:3]}
        _cache_set(ck, result)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/marches/indices", methods=["GET"])
@require_auth
def marches_indices():
    import requests as _req
    cached = _cache_get("indices", 180)
    if cached: return jsonify(cached), 200
    symbols = [
        {"ticker":"^GSPC","nom":"S&P 500","region":"USA","devise":"USD"},
        {"ticker":"^FCHI","nom":"CAC 40","region":"France","devise":"EUR"},
        {"ticker":"^DJI","nom":"Dow Jones","region":"USA","devise":"USD"},
        {"ticker":"^IXIC","nom":"Nasdaq","region":"USA","devise":"USD"},
        {"ticker":"^FTSE","nom":"FTSE 100","region":"UK","devise":"GBP"},
        {"ticker":"^N225","nom":"Nikkei 225","region":"Japon","devise":"JPY"},
    ]
    hdrs = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
    result = []
    for s in symbols:
        try:
            r = _req.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s['ticker']}?interval=1d&range=5d", timeout=6, headers=hdrs)
            d = r.json(); meta = d["chart"]["result"][0]["meta"]
            closes = [c for c in d["chart"]["result"][0]["indicators"]["quote"][0].get("close",[]) if c]
            prix = meta.get("regularMarketPrice") or meta.get("previousClose",0)
            prev = meta.get("previousClose") or (closes[-2] if len(closes)>=2 else prix)
            result.append({**s,"prix":round(prix,2),"variation_24h":round(((prix-prev)/prev*100) if prev else 0,2),
                "previous_close":round(prev,2),"sparkline":[round(c,2) for c in closes[-10:]]})
        except Exception as ex:
            result.append({**s,"prix":0,"variation_24h":0,"previous_close":0,"sparkline":[],"error":str(ex)})
    _cache_set("indices", result)
    return jsonify(result), 200

@app.route("/api/marches/indices/<path:index_ticker>/chart", methods=["GET"])
@require_auth
def marches_index_chart(index_ticker):
    import requests as _req, datetime as _dt
    days = request.args.get("days","30")
    ck = f"idx_chart_{index_ticker}_{days}"
    cached = _cache_get(ck, 300)
    if cached: return jsonify(cached), 200
    try:
        range_map={"7":"5d","30":"1mo","90":"3mo","365":"1y"}
        r = _req.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{index_ticker}?interval=1d&range={range_map.get(days,'1mo')}",
            timeout=10, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
        res0 = r.json()["chart"]["result"][0]
        ts = res0["timestamp"]; closes = res0["indicators"]["quote"][0].get("close",[])
        chart = [{"ts":ts[i]*1000,"date":_dt.datetime.utcfromtimestamp(ts[i]).strftime("%d/%m"),"prix":round(closes[i],2)}
                 for i in range(len(ts)) if closes[i]]
        _cache_set(ck, chart)
        return jsonify(chart), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/marches/indices/<path:index_ticker>/companies", methods=["GET"])
@require_auth
def marches_index_companies(index_ticker):
    import requests as _req
    page = int(request.args.get("page",1))
    q = request.args.get("q","").lower().strip()
    per_pg = 25
    all_cos = _INDEX_STOCKS.get(index_ticker, [])
    filtered = [(t,n) for t,n in all_cos if q in t.lower() or q in n.lower()] if q else all_cos
    total = len(filtered)
    page_list = filtered[(page-1)*per_pg:page*per_pg]
    hdrs = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
    result = []
    for ticker, nom in page_list:
        ck = f"px_{ticker}"
        cached = _cache_get(ck, 300)
        if cached: result.append(cached); continue
        prix, var, prev = _fetch_price(ticker, hdrs, _req)
        item = {"ticker":ticker,"nom":nom,"prix":prix,"variation_24h":var,"previous_close":prev,"devise":_get_devise(ticker)}
        _cache_set(ck, item); result.append(item)
    return jsonify({"companies":result,"total":total,"page":page,"pages":(total+per_pg-1)//per_pg,"per_page":per_pg}), 200

@app.route("/api/marches/indices/<path:index_ticker>/stocks", methods=["GET"])
@require_auth
def marches_index_stocks(index_ticker):
    return marches_index_companies(index_ticker)



# ── Wallet crypto (lecture seule) ────────────────────────────────────────────

ETHERSCAN_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
USDT_ERC20_CONTRACT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDT_SPL_MINT       = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

VALID_NETWORKS = {"btc", "eth", "sol", "usdt_erc20", "usdt_spl", "usdt_trc20"}

EUR_TO_FCFA = 655.957  # Parité fixe UEMOA — 1 EUR = 655.957 FCFA

def _fcfa_rates():
    """Retourne les taux en FCFA et USD pour BTC/ETH/SOL/USDT depuis CoinGecko."""
    cached = _cache_get("fcfa_rates", 120)
    if cached: return cached
    try:
        import requests as _req
        r = _req.get(
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,ethereum,solana,tether&vs_currencies=eur,usd",
            timeout=10, headers={"Accept":"application/json"})
        if r.status_code == 200:
            d = r.json()
            def to_fcfa(coin, fallback_fcfa):
                eur = d.get(coin, {}).get("eur")
                return round(eur * EUR_TO_FCFA) if eur else fallback_fcfa
            def to_usd(coin, fallback_usd):
                return d.get(coin, {}).get("usd") or fallback_usd
            rates = {
                "btc":  to_fcfa("bitcoin",  63000000), "btc_usd":  to_usd("bitcoin",  68000),
                "eth":  to_fcfa("ethereum",  2300000), "eth_usd":  to_usd("ethereum",   2500),
                "sol":  to_fcfa("solana",     150000), "sol_usd":  to_usd("solana",      160),
                "usdt": to_fcfa("tether",        656), "usdt_usd": to_usd("tether",        1),
            }
            _cache_set("fcfa_rates", rates)
            return rates
    except:
        pass
    return {
        "btc":63000000,"btc_usd":68000,
        "eth":2300000,"eth_usd":2500,
        "sol":150000,"sol_usd":160,
        "usdt":656,"usdt_usd":1,
    }

def _fetch_btc_balance(address):
    import requests as _req
    r = _req.get(f"https://blockstream.info/api/address/{address}", timeout=10)
    r.raise_for_status()
    d = r.json()
    funded = d.get("chain_stats",{}).get("funded_txo_sum",0)
    spent  = d.get("chain_stats",{}).get("spent_txo_sum",0)
    return (funded - spent) / 1e8

def _fetch_eth_balance(address):
    import requests as _req
    url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest"
    if ETHERSCAN_KEY: url += f"&apikey={ETHERSCAN_KEY}"
    r = _req.get(url, timeout=10); d = r.json()
    if d.get("status") == "1": return int(d["result"]) / 1e18
    raise ValueError(d.get("message","Etherscan error"))

def _fetch_usdt_erc20_balance(address):
    import requests as _req
    url = (f"https://api.etherscan.io/api?module=account&action=tokenbalance"
           f"&contractaddress={USDT_ERC20_CONTRACT}&address={address}&tag=latest")
    if ETHERSCAN_KEY: url += f"&apikey={ETHERSCAN_KEY}"
    r = _req.get(url, timeout=10); d = r.json()
    if d.get("status") == "1": return int(d["result"]) / 1e6
    raise ValueError(d.get("message","Etherscan USDT error"))

def _fetch_sol_balance(address):
    import requests as _req
    r = _req.post("https://api.mainnet-beta.solana.com",
        json={"jsonrpc":"2.0","id":1,"method":"getBalance","params":[address]},
        timeout=10, headers={"Content-Type":"application/json"})
    return r.json().get("result",{}).get("value",0) / 1e9

def _fetch_usdt_spl_balance(address):
    import requests as _req
    r = _req.post("https://api.mainnet-beta.solana.com",
        json={"jsonrpc":"2.0","id":1,"method":"getTokenAccountsByOwner",
              "params":[address,{"mint":USDT_SPL_MINT},{"encoding":"jsonParsed"}]},
        timeout=10, headers={"Content-Type":"application/json"})
    total = 0.0
    for acc in r.json().get("result",{}).get("value",[]):
        amt = acc.get("account",{}).get("data",{}).get("parsed",{}).get("info",{}).get("tokenAmount",{})
        total += float(amt.get("uiAmount") or 0)
    return total

def _fetch_usdt_trc20_balance(address):
    import requests as _req
    try:
        r = _req.get(f"https://apilist.tronscanapi.com/api/accountv2?address={address}", timeout=10)
        for token in r.json().get("trc20token_balances",[]):
            if token.get("tokenAbbr","").upper() == "USDT":
                return float(token.get("balance",0)) / 1e6
    except: pass
    try:
        r2 = _req.get(f"https://apilist.tronscanapi.com/api/account/tokens?address={address}&start=0&limit=20", timeout=10)
        for token in r2.json().get("data",[]):
            if token.get("tokenAbbr","").upper() == "USDT":
                return float(token.get("quantity",0))
    except: pass
    return 0.0

def _get_balance(network, address):
    """Retourne (balance, balance_fcfa, balance_usd, coin_key)."""
    rates = _fcfa_rates()
    mapping = {
        "btc":       (_fetch_btc_balance,         "btc"),
        "eth":       (_fetch_eth_balance,          "eth"),
        "sol":       (_fetch_sol_balance,          "sol"),
        "usdt_erc20":(_fetch_usdt_erc20_balance,  "usdt"),
        "usdt_spl":  (_fetch_usdt_spl_balance,    "usdt"),
        "usdt_trc20":(_fetch_usdt_trc20_balance,  "usdt"),
    }
    if network not in mapping:
        return 0, 0, 0.0, "usdt"
    fetch_fn, coin_key = mapping[network]
    bal = fetch_fn(address)
    bal_fcfa = round(bal * rates[coin_key])
    bal_usd  = round(bal * rates[coin_key + "_usd"], 2)
    return bal, bal_fcfa, bal_usd, coin_key

@app.route("/api/wallet/addresses", methods=["GET"])
@require_auth
def wallet_list():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT id,network,address,label,created_at FROM wallet_addresses WHERE user_id=%s ORDER BY created_at", (request.user_id,))
        rows = cur.fetchall()
        return jsonify([{"id":r[0],"network":r[1],"address":r[2],"label":r[3],"created_at":str(r[4])} for r in rows]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/addresses", methods=["POST"])
@require_auth
def wallet_add():
    body = request.get_json() or {}
    network = body.get("network","").strip().lower()
    address = body.get("address","").strip()
    label   = body.get("label","").strip()
    if not network or not address:
        return jsonify({"error": "network et address requis"}), 400
    if network not in VALID_NETWORKS:
        return jsonify({"error": f"Réseau non supporté. Valeurs: {', '.join(VALID_NETWORKS)}"}), 400
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("INSERT INTO wallet_addresses (user_id,network,address,label) VALUES (%s,%s,%s,%s) RETURNING id",
                    (request.user_id, network, address, label))
        new_id = cur.fetchone()[0]; conn.commit()
        return jsonify({"ok":True,"id":new_id}), 201
    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({"error": "Cette adresse est déjà enregistrée pour ce réseau"}), 409
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/addresses/<int:addr_id>", methods=["DELETE"])
@require_auth
def wallet_delete(addr_id):
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM wallet_addresses WHERE id=%s AND user_id=%s RETURNING id", (addr_id, request.user_id))
        if not cur.fetchone(): return jsonify({"error": "Adresse introuvable"}), 404
        conn.commit()
        return jsonify({"ok":True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/balances", methods=["GET"])
@require_auth
def wallet_balances():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT id,network,address,label FROM wallet_addresses WHERE user_id=%s ORDER BY created_at", (request.user_id,))
        rows = cur.fetchall()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    rates = _fcfa_rates()
    result = []; total_fcfa = 0; total_usd = 0.0
    for row_id, network, address, label in rows:
        ck = f"wallet_{network}_{address}"
        cached = _cache_get(ck, 60)
        if cached:
            result.append(cached); total_fcfa += cached.get("balance_fcfa",0); continue
        try:
            bal, bal_fcfa, bal_usd, coin_key = _get_balance(network, address)
            item = {"id":row_id,"network":network,"address":address,"label":label,
                    "balance":round(bal,8),"balance_fcfa":bal_fcfa,"balance_usd":bal_usd,
                    "taux_fcfa":rates.get(coin_key,656),"taux_usd":rates.get(coin_key+"_usd",1),"error":None}
        except Exception as e:
            item = {"id":row_id,"network":network,"address":address,"label":label,
                    "balance":0,"balance_fcfa":0,"balance_usd":0.0,"taux_fcfa":0,"taux_usd":0,"error":str(e)}
        _cache_set(ck, item); result.append(item); total_fcfa += item.get("balance_fcfa",0); total_usd += item.get("balance_usd",0.0)
    return jsonify({"addresses":result,"total_fcfa":total_fcfa,"total_usd":round(total_usd,2),"rates":rates}), 200

@app.route("/api/wallet/balance/<network>/<path:address>", methods=["GET"])
@require_auth
def wallet_single_balance(network, address):
    if network not in VALID_NETWORKS:
        return jsonify({"error": "Réseau non supporté"}), 400
    try:
        bal, bal_fcfa, bal_usd, coin_key = _get_balance(network, address)
        rates = _fcfa_rates()
        item = {"network":network,"address":address,"balance":round(bal,8),
                "balance_fcfa":bal_fcfa,"balance_usd":bal_usd,
                "taux_fcfa":rates.get(coin_key,656),"taux_usd":rates.get(coin_key+"_usd",1)}
        _cache_set(f"wallet_{network}_{address}", item)
        return jsonify(item), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/stats", methods=["GET"])
@require_auth
@require_admin
def admin_stats():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users"); total_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE is_admin=TRUE"); total_admins = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE last_login > NOW()-INTERVAL '30 days'"); active_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE last_login > NOW()-INTERVAL '7 days'"); active_7j = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE created_at > NOW()-INTERVAL '30 days'"); new_30j = cur.fetchone()[0]
        return jsonify({"total_users":total_users,"total_admins":total_admins,
                        "active_users":active_users,"active_7j":active_7j,"new_30j":new_30j}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users", methods=["GET"])
@require_auth
@require_admin
def admin_list_users():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT id,email,nom,is_admin,created_at,last_login FROM users ORDER BY created_at DESC")
        rows = cur.fetchall()
        return jsonify({"users":[{"id":r[0],"email":r[1],"nom":r[2],"is_admin":r[3],
                                   "created_at":str(r[4]),"last_login":str(r[5])} for r in rows]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/user/<int:uid>/promote", methods=["POST"])
@require_auth
@require_admin
def admin_promote(uid):
    try:
        body = request.get_json() or {}
        is_admin = bool(body.get("is_admin", True))
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE users SET is_admin=%s WHERE id=%s", (is_admin, uid))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/user/<int:uid>/reset", methods=["POST"])
@require_auth
@require_admin
def admin_reset_data(uid):
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM patrimoine_data WHERE user_id=%s", (uid,))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/user/<int:uid>", methods=["DELETE"])
@require_auth
@require_admin
def admin_delete_user(uid):
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s", (uid,))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/user/<int:uid>/data", methods=["GET"])
@require_auth
@require_admin
def admin_get_user_data(uid):
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT data FROM patrimoine_data WHERE user_id=%s", (uid,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return jsonify(row[0] if row else {}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/settings", methods=["GET"])
@require_auth
@require_admin
def admin_get_settings():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT key, value FROM site_settings")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify({r[0]: json.loads(r[1]) for r in rows}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/settings", methods=["POST"])
@require_auth
@require_admin
def admin_update_settings():
    try:
        body = request.get_json() or {}
        conn = get_conn(); cur = conn.cursor()
        for key, value in body.items():
            cur.execute("""INSERT INTO site_settings (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()""",
                (key, json.dumps(value)))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/settings", methods=["GET"])
def public_settings():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT value FROM site_settings WHERE key='hidden_tabs'")
        row = cur.fetchone()
        cur.close(); conn.close()
        return jsonify({"hidden_tabs": json.loads(row[0]) if row else []}), 200
    except Exception as e:
        return jsonify({"hidden_tabs": []}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_ENV") == "development")
