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
    question = body.get("question","")
    if not question:
        return jsonify({"error": "Question requise"}), 400
    groq_key = os.environ.get("GROQ_API_KEY","")
    if not groq_key:
        return jsonify({"reponse": "Configurez GROQ_API_KEY dans .env pour activer l\'IA."}), 200
    try:
        import requests as _req
        r = _req.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={"model":"llama-3.3-70b-versatile","messages":[
                {"role":"system","content":"Tu es un conseiller financier expert pour la Cote d\'Ivoire (FCFA/UEMOA). Reponds en francais, sois concis et pratique."},
                {"role":"user","content":question}],"max_tokens":500,"temperature":0.7}, timeout=15)
        data = r.json()
        reponse = data["choices"][0]["message"]["content"]
        return jsonify({"reponse": reponse}), 200
    except Exception as e:
        return jsonify({"reponse": f"Erreur IA: {str(e)}"}), 200


# ── Données statiques BRVM ────────────────────────────────────────────────────
_BRVM_STATIC = [
    {"nom":"SONATEL CI","prix":15800,"variation_24h":0.64,"volume":1200,"devise":"FCFA"},
    {"nom":"ORANGE CI","prix":12500,"variation_24h":-0.24,"volume":980,"devise":"FCFA"},
    {"nom":"ECOBANK TG","prix":16,"variation_24h":0.0,"volume":5000,"devise":"FCFA"},
    {"nom":"SITAB CI","prix":56300,"variation_24h":1.1,"volume":420,"devise":"FCFA"},
    {"nom":"SOLIBRA CI","prix":185000,"variation_24h":0.0,"volume":30,"devise":"FCFA"},
    {"nom":"BOA CI","prix":6500,"variation_24h":-0.77,"volume":2100,"devise":"FCFA"},
    {"nom":"SGBCI","prix":12000,"variation_24h":0.42,"volume":760,"devise":"FCFA"},
    {"nom":"NSIA BANQUE CI","prix":6600,"variation_24h":0.15,"volume":1500,"devise":"FCFA"},
    {"nom":"SIB CI","prix":5400,"variation_24h":-0.37,"volume":1900,"devise":"FCFA"},
    {"nom":"TOTAL CI","prix":2500,"variation_24h":0.0,"volume":3200,"devise":"FCFA"},
    {"nom":"PALMCI","prix":7700,"variation_24h":0.52,"volume":840,"devise":"FCFA"},
    {"nom":"SICOR CI","prix":5800,"variation_24h":-0.17,"volume":610,"devise":"FCFA"},
    {"nom":"CFAO CI","prix":850,"variation_24h":0.0,"volume":420,"devise":"FCFA"},
    {"nom":"SAPH CI","prix":4490,"variation_24h":0.22,"volume":280,"devise":"FCFA"},
    {"nom":"CIE CI","prix":1500,"variation_24h":-0.33,"volume":1100,"devise":"FCFA"},
]

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
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1&sparkline=true&price_change_percentage=24h,7d"
        r = _req.get(url, timeout=10, headers={"Accept":"application/json"})
        if r.status_code == 429:
            return jsonify({"error": "Limite API CoinGecko - reessayez dans 60s", "rate_limit": True}), 429
        data = r.json()
        result = [{"id":c["id"],"symbol":c["symbol"].upper(),"nom":c["name"],
            "prix":c["current_price"],"variation_24h":round(c.get("price_change_percentage_24h") or 0,2),
            "variation_7j":round(c.get("price_change_percentage_7d_in_currency") or 0,2),
            "market_cap":c.get("market_cap",0),"volume_24h":c.get("total_volume",0),
            "image":c.get("image",""),"high_24h":c.get("high_24h",0),"low_24h":c.get("low_24h",0),
            "sparkline":(c.get("sparkline_in_7d") or {}).get("price",[])[-24:]}
            for c in (data if isinstance(data,list) else [])]
        _cache_set("crypto", result)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

@app.route("/api/marches/brvm", methods=["GET"])
@require_auth
def marches_brvm():
    import requests as _req
    cached = _cache_get("brvm", 600)
    if cached: return jsonify(cached), 200
    try:
        bs4_ok = True
        try: from bs4 import BeautifulSoup
        except ImportError: bs4_ok = False
        rows = []
        if bs4_ok:
            try:
                r = _req.get("https://www.brvm.org/fr/cours-des-actions/0/", timeout=10, headers={"User-Agent":"Mozilla/5.0"})
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(r.text, "html.parser")
                table = soup.find("table",{"id":"DataTables_Table_0"}) or soup.find("table",class_="table")
                if table:
                    for tr in table.find_all("tr")[1:]:
                        tds = tr.find_all("td")
                        if len(tds) >= 4:
                            try:
                                def clean(t): return t.get_text(strip=True).replace("\xa0","").replace(" ","").replace(",",".")
                                nom=tds[0].get_text(strip=True); dernier=float(clean(tds[1]) or "0")
                                var_str=clean(tds[2]).replace("%",""); variation=float(var_str) if var_str else 0.0
                                volume=int(float(clean(tds[3]))) if len(tds)>3 else 0
                                rows.append({"nom":nom,"prix":dernier,"variation_24h":round(variation,2),"volume":volume,"devise":"FCFA"})
                            except: pass
            except: pass
        if not rows: rows = _BRVM_STATIC
        result = {"actions":rows,"source":"brvm.org" if rows and rows[0]["nom"]!=_BRVM_STATIC[0]["nom"] else "cache_statique"}
        _cache_set("brvm", result)
        return jsonify(result), 200
    except Exception as e:
        _cache_set("brvm", {"actions":_BRVM_STATIC,"source":"cache_statique"})
        return jsonify({"actions":_BRVM_STATIC,"source":"cache_statique"}), 200

# ── Admin routes ──────────────────────────────────────────────────────────────
@app.route("/api/admin/stats", methods=["GET"])
@require_auth
@require_admin
def admin_stats():
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users"); total_users=cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE is_admin=TRUE"); total_admins=cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE last_login > NOW()-INTERVAL '30 days'"); active_users=cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE last_login > NOW()-INTERVAL '7 days'"); active_7j=cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE created_at > NOW()-INTERVAL '30 days'"); new_30j=cur.fetchone()[0]
        return jsonify({"total_users":total_users,"total_admins":total_admins,"active_users":active_users,"active_7j":active_7j,"new_30j":new_30j}), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/admin/users", methods=["GET"])
@require_auth
@require_admin
def admin_list_users():
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("SELECT u.id,u.email,u.nom,u.is_admin,u.created_at,u.last_login,pd.data FROM users u LEFT JOIN patrimoine_data pd ON pd.user_id=u.id ORDER BY u.created_at DESC")
        rows=cur.fetchall(); result=[]
        for row in rows:
            uid,email,nom,is_admin,created_at,last_login,data_raw=row
            data=data_raw if isinstance(data_raw,dict) else (json.loads(data_raw) if data_raw else {})
            profil=data.get("profil",{}); periodes=data.get("periodes",{})
            mois_actif=data.get("moisActif","")
            if not mois_actif and periodes: mois_actif=sorted(periodes.keys())[-1]
            p=periodes.get(mois_actif,{})
            rev_list=p.get("revenus",[]); dep_list=p.get("depenses",[]); alloc=p.get("allocations",0) or 0
            total_rev=sum(r.get("montant",0) for r in rev_list); total_dep=sum(d.get("montant",0) for d in dep_list)
            objectifs=data.get("objectifs",[]); patrimoine=data.get("patrimoine",[]); transactions=data.get("transactions",[])
            total_actifs=sum(a.get("valeurActuelle",0) for a in patrimoine)
            total_epargne=sum(o.get("epargne",0) for o in objectifs)
            historique=[{"mois":m,"revenus":sum(x.get("montant",0) for x in periodes[m].get("revenus",[])),
                "depenses":sum(x.get("montant",0) for x in periodes[m].get("depenses",[])),
                "allocations":periodes[m].get("allocations",0) or 0,
                "nb_revenus":len(periodes[m].get("revenus",[])),"nb_depenses":len(periodes[m].get("depenses",[]))}
                for m in sorted(periodes.keys(),reverse=True)]
            result.append({"id":uid,"email":email,"nom":nom,"is_admin":is_admin,
                "created_at":created_at.isoformat() if created_at else None,
                "last_login":last_login.isoformat() if last_login else None,
                "mois_actif":mois_actif,"profil_risque":profil.get("profilRisque",""),
                "revenu":profil.get("revenuMensuel",0),"nb_mois":len(periodes),
                "nb_transactions":len(transactions),"nb_actifs":len(patrimoine),"nb_objectifs":len(objectifs),
                "revenus":total_rev,"depenses":total_dep,"allocations":alloc,"solde":total_rev-total_dep-alloc,
                "patrimoine_net":total_actifs+total_epargne+(total_rev-total_dep-alloc),
                "total_actifs":total_actifs,"total_epargne_obj":total_epargne,
                "lignes_revenus":rev_list,"lignes_depenses":dep_list,"actifs":patrimoine,
                "objectifs":objectifs,"transactions_recentes":transactions,"historique_mois":historique})
        return jsonify({"users":result}), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@require_auth
@require_admin
def admin_delete_user(uid):
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("DELETE FROM patrimoine_data WHERE user_id=%s",(uid,))
        cur.execute("DELETE FROM users WHERE id=%s",(uid,)); conn.commit()
        return jsonify({"ok":True}), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/admin/users/<int:uid>/reset-data", methods=["POST"])
@require_auth
@require_admin
def admin_reset_data(uid):
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("UPDATE patrimoine_data SET data='{}'::jsonb WHERE user_id=%s",(uid,)); conn.commit()
        return jsonify({"ok":True}), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/admin/users/<int:uid>/toggle-admin", methods=["POST"])
@require_auth
@require_admin
def admin_toggle_admin(uid):
    if uid==request.user_id: return jsonify({"error":"Impossible de modifier vos propres droits"}), 400
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("UPDATE users SET is_admin=NOT is_admin WHERE id=%s RETURNING is_admin",(uid,))
        row=cur.fetchone(); conn.commit()
        if not row: return jsonify({"error":"Utilisateur introuvable"}), 404
        return jsonify({"is_admin":row[0]}), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/admin/users/<int:uid>/data", methods=["GET"])
@require_auth
@require_admin
def admin_get_user_data(uid):
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("SELECT data FROM patrimoine_data WHERE user_id=%s",(uid,))
        row=cur.fetchone()
        if not row: return jsonify({}), 200
        data=row[0] if isinstance(row[0],dict) else json.loads(row[0])
        return jsonify(data), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/admin/users/<int:uid>/month/<mois>", methods=["GET"])
@require_auth
@require_admin
def admin_get_user_month(uid, mois):
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("SELECT data FROM patrimoine_data WHERE user_id=%s",(uid,))
        row=cur.fetchone()
        if not row: return jsonify({"mois":mois,"revenus":[],"depenses":[],"allocations":0,"total_revenus":0,"total_depenses":0}), 200
        data=row[0] if isinstance(row[0],dict) else json.loads(row[0])
        p=data.get("periodes",{}).get(mois,{})
        rev=p.get("revenus",[]); dep=p.get("depenses",[]); alloc=p.get("allocations",0) or 0
        return jsonify({"mois":mois,"revenus":rev,"depenses":dep,"allocations":alloc,
            "total_revenus":sum(r.get("montant",0) for r in rev),
            "total_depenses":sum(d.get("montant",0) for d in dep)}), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/admin/promote", methods=["POST"])
def admin_promote():
    secret=os.environ.get("ADMIN_SECRET","")
    if not secret: return jsonify({"error":"ADMIN_SECRET non configure"}), 403
    body=request.get_json() or {}
    if body.get("secret")!=secret: return jsonify({"error":"Secret invalide"}), 403
    email=(body.get("email","")).strip()
    if not email: return jsonify({"error":"email requis"}), 400
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("UPDATE users SET is_admin=TRUE WHERE email=%s RETURNING id,email",(email,))
        row=cur.fetchone(); conn.commit()
        if not row: return jsonify({"error":"Utilisateur introuvable"}), 404
        return jsonify({"ok":True,"id":row[0],"email":row[1]}), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
