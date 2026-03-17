#!/bin/bash

# --- CONFIGURATION ---
PORT_HTTPS=8443
NETWORK_NAME="dslab-net"
CERT_FILE="./dslab.crt"
KEY_FILE="./dslab.key"

echo "🚀 Initialisation de l'infrastructure DSLab..."

# 1. Vérification/Génération des certificats SSL
if [[ ! -f "$CERT_FILE" || ! -f "$KEY_FILE" ]]; then
    echo "🔐 Certificats SSL manquants. Génération de nouveaux certificats..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout "$KEY_FILE" -out "$CERT_FILE" \
      -subj "/C=CM/L=Ngaoundere/O=UN/CN=localhost"
    echo "✅ Certificats générés (dslab.crt, dslab.key)."
else
    echo "🔐 Certificats SSL détectés."
fi

echo "🚀 Démarrage de l'infrastructure DSLab..."

# 1. Vérification du réseau
if ! podman network exists $NETWORK_NAME; then
    echo "🌐 Création du réseau $NETWORK_NAME..."
    podman network create $NETWORK_NAME
fi

# 2. Nettoyage des anciens conteneurs
echo "🧹 Nettoyage des conteneurs existants..."
podman-compose down

# 3. Lancement des services
echo "📦 Lancement des services (Traefik, Web, Hub)..."
podman-compose up -d

# 4. Attente du démarrage de Traefik
echo "⏳ Attente de l'initialisation du tunnel..."
sleep 5

# 5. Récupération de l'IP locale pour information
IP_LOCALE=$(hostname -I | awk '{print $1}')

echo "-------------------------------------------------------"
echo "✅ Infrastructure démarrée avec succès !"
echo "🔗 Accès Local : https://localhost:$PORT_HTTPS"
echo "🌐 Accès Réseau : https://$IP_LOCALE:$PORT_HTTPS"
echo "🛠️  Logs Traefik : podman logs -f traefik"
echo "-------------------------------------------------------"

# 6. Optionnel : Lancement automatique de Ngrok si présent
if command -v ngrok &> /dev/null
then
    echo "🔌 Lancement du tunnel Ngrok sur le port $PORT_HTTPS..."
    echo "👉 Ton interface sera bientôt disponible sur ton URL Ngrok publique."
    ngrok http https://localhost:$PORT_HTTPS
else
    echo "⚠️  Ngrok n'est pas installé, tunnel public non démarré."
fi