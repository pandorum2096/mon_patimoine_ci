# 💰 Mon Patrimoine CI

Application web open source de gestion financière personnelle conçue pour la Côte d'Ivoire et l'espace UEMOA. Elle permet à chaque utilisateur de suivre ses revenus, dépenses, épargnes, investissements et patrimoine en FCFA, avec un accompagnement IA personnalisé.

> Développé avec ❤️ pour aider la population ivoirienne à mieux gérer ses finances, épargner et investir intelligemment.

---

## 🌟 Fonctionnalités

### 9 onglets complets
- **Accueil** — Tableau de bord avec score de santé financière /100, solde du mois, résumé des revenus/dépenses/épargne et conseil du jour
- **Budget** — Saisie des revenus, dépenses et transactions par mois. Règle 50/30/20 intégrée
- **Graphiques** — Évolution du solde, répartition des dépenses, comparatif revenus/dépenses (Recharts)
- **Objectifs** — Création et suivi d'objectifs financiers avec barre de progression (ex : achat terrain, fonds d'urgence)
- **Investir** — Tableau de bord marchés financiers en temps réel : cryptos, indices boursiers mondiaux, BRVM
- **Conseil** — Simulateur d'intérêts composés/simples + conseil IA personnalisé par Marie-Claire Koné (voir section IA)
- **Patrimoine** — Inventaire des actifs (immobilier, véhicules, placements…) et calcul du patrimoine net
- **Formation** — Modules éducatifs sur les finances CI : BRVM, Djamo, Orange Money, arnaques, terrain CI…
- **Profil** — Gestion du compte, profil de risque investisseur, revenu mensuel de référence

### Sécurité & multi-utilisateurs
- Authentification JWT (token stocké côté client)
- Mots de passe hachés avec bcrypt
- Chaque utilisateur a ses propres données isolées en base

### IA Conseillère
- Analyse automatique de la situation financière du mois
- Réponse structurée signée **Marie-Claire Koné**, conseillère fictive basée à Abidjan
- Fonctionne via **Groq API** (recommandé, rapide, gratuit) ou **Ollama local** (LLM hors ligne)

---

## 🏗️ Architecture

```
mon_patimoine_ci/
│
├── app.py                   # Backend Flask — API REST, auth JWT, conseil IA, données marchés
├── server.py                # Serveur alternatif / point d'entrée secondaire
├── init_db.py               # Script d'initialisation de la base PostgreSQL
├── requirements.txt         # Dépendances Python
│
├── index.html               # Frontend React (single-file, Babel CDN, servi par Flask)
├── MonPatrimoineCI.jsx      # Code source React — tous les composants et onglets
│
├── Dockerfile               # Image Docker Flask
├── docker-compose.yml       # Stack complète : Flask + PostgreSQL + Ollama
├── docker-compose.gpu.yml   # Variante avec support GPU NVIDIA pour Ollama
│
├── render.yaml              # Configuration déploiement Render.com
├── demarrer.bat             # Script de démarrage rapide Windows
├── .env                     # Variables d'environnement locales (non committé)
└── .env.example             # Modèle de configuration
```

**Flask** sert à la fois l'API (`/api/*`) et le fichier `index.html` comme frontend single-page. La base de données est **PostgreSQL**. Le frontend est du React chargé via CDN (Babel + Recharts), sans étape de build.

---

## 📡 API Endpoints

### Authentification
| Méthode | Route | Auth | Description |
|---------|-------|:----:|-------------|
| POST | `/api/register` | ❌ | Créer un compte |
| POST | `/api/login` | ❌ | Se connecter, reçoit un token JWT |
| GET | `/api/me` | ✅ | Infos du compte connecté |
| POST | `/api/change-password` | ✅ | Changer le mot de passe |
| DELETE | `/api/delete-account` | ✅ | Supprimer le compte et toutes les données |

### Données financières
| Méthode | Route | Auth | Description |
|---------|-------|:----:|-------------|
| GET | `/api/load` | ✅ | Charger toutes les données de l'utilisateur |
| POST | `/api/save` | ✅ | Sauvegarder les données |
| POST | `/api/update-profile` | ✅ | Mettre à jour le profil (nom, revenu, profil risque) |
| GET | `/api/export` | ✅ | Export JSON complet des données |

### Intelligence Artificielle
| Méthode | Route | Auth | Description |
|---------|-------|:----:|-------------|
| POST | `/api/conseil-ia` | ✅ | Analyse IA de la situation financière du mois |

### Marchés financiers
| Méthode | Route | Auth | Description |
|---------|-------|:----:|-------------|
| GET | `/api/marches/crypto` | ❌ | Liste des cryptomonnaies (top 20) |
| GET | `/api/marches/crypto/<id>` | ❌ | Détail + historique d'une crypto |
| GET | `/api/marches/indices` | ❌ | Indices boursiers mondiaux |
| GET | `/api/marches/indices/<ticker>/chart` | ❌ | Historique graphique d'un indice |
| GET | `/api/marches/indices/<ticker>/companies` | ❌ | Entreprises d'un indice |
| GET | `/api/marches/indices/<ticker>/stocks` | ❌ | Cours des actions d'un indice |
| GET | `/api/marches/brvm` | ❌ | Cours des actions BRVM (Bourse CI) |

### Administration
| Méthode | Route | Auth | Description |
|---------|-------|:----:|-------------|
| GET | `/api/admin/stats` | ✅ Admin | Statistiques globales de l'app |
| GET | `/api/admin/users` | ✅ Admin | Liste des utilisateurs |
| GET | `/health` | ❌ | Health check (utilisé par Docker) |

---

## ⚙️ Variables d'environnement

Copiez `.env.example` en `.env` et remplissez les valeurs :

```env
# Base de données PostgreSQL (obligatoire)
DATABASE_URL=postgresql://user:password@host:5432/patrimoine

# Clé secrète JWT — générez une valeur aléatoire longue (obligatoire)
SECRET_KEY=changez-cette-cle-en-production

# IA Groq (recommandé — gratuit sur groq.com)
GROQ_API_KEY=gsk_...

# Environnement
FLASK_ENV=development
PORT=5000
```

> Si `GROQ_API_KEY` est absent, l'IA bascule automatiquement sur Ollama local (`http://ollama:11434`).

---

## 🚀 Lancement local (sans Docker)

### Prérequis
- Python 3.10+
- PostgreSQL local ou compte gratuit sur [neon.tech](https://neon.tech)

```bash
# 1. Cloner le projet
git clone https://github.com/votre-compte/mon-patrimoine-ci
cd mon-patrimoine-ci

# 2. Installer les dépendances Python
pip install -r requirements.txt

# 3. Configurer l'environnement
cp .env.example .env
# Éditez .env : renseignez DATABASE_URL et SECRET_KEY

# 4. Initialiser la base de données
python init_db.py

# 5. Lancer le serveur
python app.py
```

Ouvrez [http://localhost:5000](http://localhost:5000)

---

## 🐳 Lancement avec Docker (stack complète + IA locale)

La stack Docker inclut Flask, PostgreSQL et Ollama (LLM local llama3).

```bash
# Lancement standard (CPU)
docker compose up -d --build

# Lancement avec GPU NVIDIA (génération IA 3-5× plus rapide)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

> Au premier lancement, Ollama télécharge automatiquement le modèle `llama3` (~4.7 Go). Les modèles sont stockés dans un volume Docker persistant (`ollama_data`).

### Accès
- App : [http://localhost:5000](http://localhost:5000)
- Ollama (si port décommenté) : [http://localhost:11434](http://localhost:11434)

### Commandes utiles

```bash
# Voir les logs en temps réel
docker compose logs -f web

# Redémarrer uniquement Flask après une modification de app.py
docker compose restart web

# Arrêter toute la stack
docker compose down

# Télécharger un autre modèle IA (ex: mistral)
docker compose exec ollama ollama pull mistral
```

---

## 🌐 Déploiement sur Render (gratuit)

### Étape 1 — Mettre le code sur GitHub

1. Créez un dépôt public `mon-patrimoine-ci` sur [github.com](https://github.com)
2. Uploadez tous les fichiers **sauf** `.env` (déjà dans `.gitignore`)

### Étape 2 — Créer la base de données PostgreSQL

1. Créez un compte gratuit sur [neon.tech](https://neon.tech)
2. Créez un projet → copiez l'URL de connexion (`postgresql://...`)

### Étape 3 — Déployer sur Render

1. Allez sur [render.com](https://render.com) → **New +** → **Web Service**
2. Connectez votre dépôt GitHub
3. Configurez :
   - **Runtime :** Python 3
   - **Build Command :** `pip install -r requirements.txt`
   - **Start Command :** `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Ajoutez les variables d'environnement :
   - `DATABASE_URL` → URL Neon
   - `SECRET_KEY` → clé aléatoire longue ([randomkeygen.com](https://randomkeygen.com))
   - `GROQ_API_KEY` → clé Groq (optionnel, pour l'IA)
5. Cliquez **Create Web Service**

✅ L'app sera disponible sur `https://mon-patrimoine-ci.onrender.com`

> Sur Render gratuit, Ollama local n'est pas disponible. Utilisez `GROQ_API_KEY` pour l'IA en production.

---

## 🤖 Conseil IA — Fonctionnement

Le bouton **"Analyser mon profil"** dans l'onglet Conseil envoie les données financières du mois à `/api/conseil-ia`. Le backend construit un prompt détaillé et contacte l'IA.

**Deux modes :**

| Mode | Condition | Modèle | Vitesse |
|------|-----------|--------|---------|
| Groq API | `GROQ_API_KEY` présent dans `.env` | llama-3.3-70b-versatile | ~3s |
| Ollama local | Pas de clé Groq, Docker actif | llama3 (ou autre) | ~30-60s CPU |

La réponse est structurée comme une lettre de conseil signée **Marie-Claire Koné**, avec introduction personnalisée, conseils titrés avec emoji, résumé numéroté et clôture professionnelle.

Pour obtenir une clé Groq gratuite : [console.groq.com](https://console.groq.com)

---

## 🤝 Contribution

Les contributions sont les bienvenues !

1. Forkez le projet
2. Créez une branche : `git checkout -b feature/ma-fonctionnalite`
3. Committez vos changements : `git commit -m "feat: description"`
4. Poussez : `git push origin feature/ma-fonctionnalite`
5. Ouvrez une Pull Request

---

## 📄 Licence

MIT License — Libre d'utilisation, de modification et de distribution.

mon_patimoine_ci/
│
├── 🐍 Backend
│   ├── app.py              — API Flask principale (auth, données, conseil IA, BRVM…)
│   ├── server.py           — Serveur alternatif / point d'entrée
│   ├── init_db.py          — Initialisation de la base de données PostgreSQL
│   └── requirements.txt    — Dépendances Python
│
├── 🌐 Frontend
│   ├── index.html          — App React compilée (fichier unique servi par Flask)
│   └── MonPatrimoineCI.jsx — Code source React (composants, onglets, UI)
│
├── 🐳 Docker
│   ├── Dockerfile              — Image Flask + app
│   ├── docker-compose.yml      — Stack complète (Flask + PostgreSQL + Ollama)
│   └── docker-compose.gpu.yml  — Variante avec support GPU pour Ollama
│
├── ⚙️ Config
│   ├── .env                — Variables d'environnement (clés API, DB…)
│   ├── .env.example        — Modèle de configuration
│   ├── .gitignore
│   ├── render.yaml         — Config déploiement Render.com
│   └── demarrer.bat        — Script de démarrage Windows
│
└── 📸 Assets
    ├── affiche_mon_patrimoine_ci.png
    └── affiche_mon_patrimoine_ci_v2.png