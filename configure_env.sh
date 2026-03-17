#!/bin/bash

# --- CONFIGURATION ---
REQUIRED_DIRS=(
    "/home/lisa/DSLab"
    "/home/lisa/workspaces"
    "/opt/ds_shared_libs"
)
DB_PATH="/home/lisa/DSLab/dslab.db"

echo "🔍 Vérification de l'environnement DSLab..."

# 1. Vérification des outils installés
echo "🛠️  Vérification des dépendances..."
for tool in podman podman-compose openssl netifaces; do
    if ! command -v $tool &> /dev/null && [[ $tool != "netifaces" ]]; then
        echo "❌ ERREUR : $tool n'est pas installé."
        exit 1
    fi
done
echo "✅ Outils de base présents."

# 2. Création et vérification des volumes/répertoires
echo "📂 Vérification des volumes..."
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "📁 Création du répertoire : $dir"
        mkdir -p "$dir"
    fi
    # Vérification des permissions
    chmod 755 "$dir"
done
echo "✅ Répertoires prêts."

# 3. Vérification de SELinux (Critique sur RHEL/Fedora/CentOS)
echo "🛡️  Vérification SELinux..."
if command -v getenforce &> /dev/null; then
    STATUS=$(getenforce)
    echo "SELinux est en mode : $STATUS"
    if [ "$STATUS" == "Enforcing" ]; then
        echo "⚙️  Application des contextes de sécurité (label :Z)..."
        # On applique le label container_file_t pour permettre à Podman d'écrire
        chcon -Rt container_file_t /home/lisa/DSLab
        chcon -Rt container_file_t /home/lisa/workspaces
    fi
else
    echo "ℹ️ SELinux n'est pas activé sur ce système."
fi

# 4. Vérification de la base de données SQLite
if [ ! -f "$DB_PATH" ]; then
    echo "⚠️  Base de données absente à $DB_PATH. Elle sera initialisée au premier lancement."
fi

# 5. Permissions sur la socket Podman (Rootless)
echo "🔌 Vérification de la socket Podman..."
if [ -S "$XDG_RUNTIME_DIR/podman/podman.sock" ]; then
    echo "✅ Socket Podman détectée."
else
    echo "❌ ERREUR : La socket Podman n'est pas active."
    echo "👉 Lance : systemctl --user enable --now podman.socket"
    exit 1
fi

echo "-------------------------------------------------------"
echo "✅ Configuration terminée avec succès !"
echo "🚀 Tu peux maintenant lancer ./start_dslab.sh"
echo "-------------------------------------------------------"