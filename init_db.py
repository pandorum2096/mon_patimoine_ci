"""
Script d'initialisation de la base de données Neon PostgreSQL.
Lancez ce script une seule fois pour créer les tables.

Usage : python init_db.py
"""

import os
import psycopg2

# Charger .env manuellement si disponible
try:
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
except FileNotFoundError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ DATABASE_URL non défini. Vérifiez votre fichier .env")
    exit(1)

print(f"🔗 Connexion à : {DATABASE_URL[:50]}...")

try:
    conn = psycopg2.connect(DATABASE_URL)
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

    # Vérification
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = [r[0] for r in cur.fetchall()]
    print(f"✅ Tables présentes : {', '.join(tables)}")

    cur.close()
    conn.close()
    print("✅ Base de données initialisée avec succès !")
    print("\n📋 Prochaines étapes :")
    print("   1. python app.py           → tester en local")
    print("   2. Publier sur GitHub")
    print("   3. Déployer sur Render avec DATABASE_URL + SECRET_KEY")

except Exception as e:
    print(f"❌ Erreur : {e}")
