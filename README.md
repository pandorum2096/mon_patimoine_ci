# 💰 Mon Patrimoine CI

Application open source de gestion financière personnelle pour la Côte d'Ivoire et l'espace UEMOA.

**Stack :** React (CDN) · Flask · PostgreSQL · JWT · Render.com

---

## 🌟 Fonctionnalités

- 9 onglets : Accueil, Budget, Graphiques, Objectifs, Investir, Conseil, Patrimoine, Formation, Profil
- Multi-utilisateurs avec comptes sécurisés
- Données en FCFA avec logique 50/30/20
- Graphiques Recharts (évolution, répartition, projections)
- Simulateur d'intérêts composés/simples
- Score de santé financière /100
- Formation financière (BRVM, Djamo, arnaques, terrain CI...)
- Thème sombre/clair

---

## 🚀 Déploiement sur Render (gratuit)

### Étape 1 — Mettre le code sur GitHub

1. Créez un compte sur [github.com](https://github.com)
2. Créez un nouveau dépôt public nommé `mon-patrimoine-ci`
3. Uploadez tous les fichiers du projet (glisser-déposer dans l'interface web)
4. Assurez-vous que `.env` **n'est pas** dans le dépôt (il est dans `.gitignore`)

### Étape 2 — Créer la base de données PostgreSQL (gratuit via Neon)

1. Allez sur [neon.tech](https://neon.tech) et créez un compte gratuit
2. Créez un nouveau projet → notez l'URL de connexion (format `postgresql://...`)

### Étape 3 — Déployer sur Render

1. Allez sur [render.com](https://render.com) et créez un compte
2. Cliquez **"New +"** → **"Web Service"**
3. Connectez votre dépôt GitHub `mon-patrimoine-ci`
4. Configurez :
   - **Runtime :** Python 3
   - **Build Command :** `pip install -r requirements.txt`
   - **Start Command :** `gunicorn app:app --bind 0.0.0.0:$PORT`
5. Ajoutez les variables d'environnement :
   - `DATABASE_URL` → l'URL Neon copiée à l'étape 2
   - `SECRET_KEY` → une chaîne aléatoire longue (ex: générez sur [randomkeygen.com](https://randomkeygen.com))
6. Cliquez **"Create Web Service"**

✅ Votre app sera disponible sur `https://mon-patrimoine-ci.onrender.com`

---

## 💻 Développement local

### Prérequis
- Python 3.10+
- PostgreSQL local ou compte Neon gratuit

```bash
# 1. Cloner le projet
git clone https://github.com/votre-compte/mon-patrimoine-ci
cd mon-patrimoine-ci

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer l'environnement
cp .env.example .env
# Éditez .env avec votre DATABASE_URL

# 4. Lancer le serveur
python app.py
```

Ouvrez [http://localhost:5000](http://localhost:5000)

---

## 🏗️ Architecture

```
mon-patrimoine-ci/
├── app.py           # Backend Flask (API REST + auth JWT)
├── index.html       # Frontend React (single-file, Babel CDN)
├── requirements.txt # Dépendances Python
├── render.yaml      # Config déploiement Render
├── .env.example     # Variables d'environnement (template)
└── .gitignore
```

### API Endpoints

| Méthode | Route | Auth | Description |
|---------|-------|------|-------------|
| POST | `/api/register` | ❌ | Créer un compte |
| POST | `/api/login` | ❌ | Se connecter |
| GET | `/api/load` | ✅ | Charger les données |
| POST | `/api/save` | ✅ | Sauvegarder les données |
| GET | `/api/export` | ✅ | Export JSON des données |
| DELETE | `/api/delete-account` | ✅ | Supprimer le compte |
| GET | `/health` | ❌ | Health check |

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Pour contribuer :

1. Forkez le projet
2. Créez une branche (`git checkout -b feature/ma-fonctionnalite`)
3. Committez vos changements
4. Ouvrez une Pull Request

---

## 📄 Licence

MIT License — Libre d'utilisation, de modification et de distribution.

---

## 🙏 Pour la population ivoirienne

Ce projet est développé avec ❤️ pour aider la population de Côte d'Ivoire à mieux gérer ses finances, épargner et investir intelligemment.
