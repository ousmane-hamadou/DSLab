Début#!/bin/bash

# --- CONFIGURATION ---
WORKSPACE_ROOT="/home/lisa/workspaces"
PROJECT_DIR="/home/lisa/DSLab"

echo "Début de la construction de l'écosystème DSLab..."

# # 1. Vérification des dossiers
# echo "📂 Préparation des répertoires..."
# sudo mkdir -p "$WORKSPACE_ROOT"
# sudo chown -R 1000:100 "$WORKSPACE_ROOT"
# sudo chmod -R 775 "$WORKSPACE_ROOT"

# 2. Construction de l'image Notebook Collaborative (Dockerfile.jupyterds)
# Cette image est utilisée dynamiquement par le DockerSpawner
echo "📦 Construction de l'image Notebook Collaborative..."
podman build -t dslab-collab:latest -f Dockerfile.jupyterds .

# 3. Lancement du build de la pile via Podman-Compose
# Cela va builder :
# - DSLab-Web (via Dockerfile)
# - JupyterHub (via Dockerfile.jupyterhub)
echo "🏗 Construction des services DSLab-Web et JupyterHub..."
podman-compose build

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ TOUT EST PRÊT !"
    echo "-------------------------------------------------------"
    echo "🌐 Accès Web via Traefik : http://localhost:8080"
    echo "📝 JupyterHub accessible : http://localhost:8080/hub"
    echo "📡 App DSLab accessible  : http://localhost:8080/"
    echo "-------------------------------------------------------"
    echo "👉 Lance maintenant : 'podman-compose up -d'"
else
    echo "❌ Erreur lors du build de la pile."
    exit 1
fi