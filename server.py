"""
Mon Patrimoine CI — Serveur local
Persistance SQLite + API REST pour l'application React

Lancement : python server.py
Accès     : http://localhost:5000
"""


import os
import json
import sqlite3
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ─── Configuration ────────────────────────────────────────────────────────────
PORT     = 5000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "patrimoine.db")
HTML_PATH = os.path.join(BASE_DIR, "index.html")

# ─── Base de données SQLite ───────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS storage (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # Table historique pour audit (bonus)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historique (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            saved_at   TEXT DEFAULT (datetime('now')),
            snapshot   TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def db_load(key):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM storage WHERE key = ?", (key,)).fetchone()
    conn.close()
    return json.loads(row[0]) if row else None

def db_save(key, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO storage (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (key, json.dumps(value, ensure_ascii=False))
    )
    # Garder un snapshot toutes les 10 sauvegardes (optionnel)
    count = conn.execute("SELECT COUNT(*) FROM historique").fetchone()[0]
    if count % 10 == 0:
        conn.execute(
            "INSERT INTO historique (snapshot) VALUES (?)",
            (json.dumps(value, ensure_ascii=False),)
        )
    conn.commit()
    conn.close()

def db_export():
    """Export complet pour sauvegarde manuelle."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value, updated_at FROM storage WHERE key = 'patrimoine_v3'").fetchone()
    conn.close()
    if row:
        return {"data": json.loads(row[0]), "updated_at": row[1]}
    return {}

# ─── Handler HTTP ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Silencieux (commenter pour voir les logs)
        pass

    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self):
        with open(HTML_PATH, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self.send_html()

        elif path == "/api/load":
            data = db_load("patrimoine_v3")
            self.send_json(200, data or {})

        elif path == "/api/export":
            self.send_json(200, db_export())

        elif path == "/api/status":
            self.send_json(200, {
                "ok": True,
                "db": DB_PATH,
                "port": PORT
            })

        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/save":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body.decode("utf-8"))
                db_save("patrimoine_v3", payload)
                self.send_json(200, {"ok": True})
            except Exception as e:
                self.send_json(400, {"error": str(e)})

        else:
            self.send_json(404, {"error": "Not found"})


# ─── Démarrage ────────────────────────────────────────────────────────────────
def open_browser():
    import time
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{PORT}")

if __name__ == "__main__":
    init_db()
    print(f"""
╔══════════════════════════════════════════════════╗
║         💰 Mon Patrimoine CI — Serveur           ║
╠══════════════════════════════════════════════════╣
║  Adresse  : http://localhost:{PORT}                ║
║  Base     : {os.path.basename(DB_PATH)}                   ║
║  Arrêt    : Ctrl+C                               ║
╚══════════════════════════════════════════════════╝
""")
    threading.Thread(target=open_browser, daemon=True).start()
    server = HTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✅ Serveur arrêté.")
