FROM python:3.12-slim

# Dépendances système : git requis par les agents (git-integration, devops-infra)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances Python — couche cachée séparément pour les rebuilds rapides
COPY engine/requirements.txt ./engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt

# Code applicatif
COPY . .

# Répertoire d'état inscriptible (state.json + events.jsonl)
RUN mkdir -p engine/state

EXPOSE 8765

# server.py fait os.chdir(ROOT) où ROOT = /app ; le port 8765 est servi depuis là.
CMD ["python", "engine/server.py"]
