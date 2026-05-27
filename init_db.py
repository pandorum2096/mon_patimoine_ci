"""
Script d'initialisation de la base de données PostgreSQL.
Lancez ce script une seule fois pour créer les tables.

Usage : python init_db.py
"""

import os
import sys

# ─── Charger .env depuis le répertoire du script (chemin absolu garanti)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ENV_PATH, override=True)
except ImportError:
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ[_k.strip()] = _v.strip()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ DATABASE_URL non défini. Vérifiez votre fichier .env")
    print(f"   Chemin cherché : {_ENV_PATH}")
    sys.exit(1)

host = DATABASE_URL.split("@")[-1].split("/")[0] if "@" in DATABASE_URL else DATABASE_URL[:40]
print(f"🔗 Connexion à : {host}...")

# ─── Compatibilité psycopg2 (Linux/Render) + pg8000 (Windows fallback)
try:
    import psycopg2
    import psycopg2.extras
    DB_DRIVER = "psycopg2"
except ImportError:
    try:
        import pg8000.native
        DB_DRIVER = "pg8000"
    except ImportError:
        print("❌ Ni psycopg2 ni pg8000 n'est installé.")
        print("   Exécutez : pip install psycopg2-binary")
        sys.exit(1)

print(f"✅ Driver DB : {DB_DRIVER}")


def get_conn():
    url = DATABASE_URL
    if DB_DRIVER == "psycopg2":
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url)
    else:
        import urllib.parse
        p = urllib.parse.urlparse(url)
        return pg8000.native.Connection(
            user=p.username, password=p.password,
            host=p.hostname, port=p.port or 5432,
            database=p.path.lstrip("/"), ssl_context=True,
        )


try:
    conn = get_conn()
    cur = conn.cursor()

    print("📦 Création des tables...")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nom           TEXT NOT NULL DEFAULT '',
            created_at    TIMESTAMP DEFAULT NOW()
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

    # Vérification des tables créées
    if DB_DRIVER == "psycopg2":
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"✅ Tables présentes : {', '.join(tables)}")
    else:
        print("✅ Tables créées (pg8000)")

    cur.close()
    conn.close()
    print("✅ Base de données initialisée avec succès !")
    print()
    print("📋 Prochaines étapes :")
    print("   1. python app.py           → tester en local")
    print("   2. Publier sur GitHub")
    print("   3. Déployer sur Render avec DATABASE_URL + SECRET_KEY")

except Exception as e:
    print(f"❌ Erreur : {e}")
    sys.exit(1)
