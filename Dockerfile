FROM python:3.11-slim

# Dépendances système pour psycopg2 + curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY app.py .
COPY index.html .

# Port exposé
EXPOSE 5000

# Gunicorn — timeout 180s pour laisser Ollama générer (LLM peut être lent)
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 60 --keep-alive 5
