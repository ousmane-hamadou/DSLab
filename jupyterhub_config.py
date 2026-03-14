import os
import sqlite3

import netifaces
from jupyterhub.auth import DummyAuthenticator

c = get_config()

# --- 1. CONFIGURATION RÉSEAU GÉNÉRALE ---
# Port pour les utilisateurs (via Traefik/Ngrok)
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# Port pour l'API interne (Communication Hub <-> Notebooks)
c.JupyterHub.hub_ip = '0.0.0.0'
c.JupyterHub.hub_port = 8888

# TRÈS IMPORTANT : Adresse DNS du Hub dans le réseau dslab-net
# On utilise l'alias défini dans docker-compose au lieu d'une IP fixe
c.JupyterHub.hub_connect_ip = 'jupyterhub'

# --- 2. AUTHENTIFICATION CUSTOM ---


class MyAuthenticator(DummyAuthenticator):
    async def authenticate(self, handler, data):
        # Récupération automatique du username (UUID) dans l'URL
        username = handler.get_argument("username", None)
        if username:
            return {"name": username}
        return await super().authenticate(handler, data)


c.JupyterHub.authenticator_class = MyAuthenticator
c.Authenticator.auto_login = True
c.Authenticator.allow_all = True
c.Authenticator.any_allow_config = True
c.Authenticator.allow_existing_users = True
c.Authenticator.admin_users = {'lisa'}
c.JupyterHub.allow_named_servers = True

# --- 3. CONFIGURATION DU SPAWNER (PODMAN / DOCKERSPAWNER) ---
c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'
c.DockerSpawner.image = 'quay.io/jupyter/datascience-notebook:latest'

# Socket Podman (Standard Fedora Rootless)
c.DockerSpawner.client_kwargs = {
    'base_url': 'unix:///var/run/docker.sock'
}

# Configuration du réseau dslab-net
network_name = 'dslab-net'
c.DockerSpawner.network_name = network_name
c.DockerSpawner.hub_connect_ip = network_name
c.DockerSpawner.args = ['--ip=0.0.0.0']
c.DockerSpawner.use_internal_ip = True

# Options spécifiques pour Podman et la stabilité
c.DockerSpawner.extra_host_config = {
    "network_mode": network_name,
}
c.DockerSpawner.extra_create_kwargs = {'user': '0'}
c.DockerSpawner.remove = False
c.Spawner.start_timeout = 300
c.Spawner.http_timeout = 180

# --- 4. HOOK DE PRÉ-LANCEMENT (DYNAMIQUE) ---


async def pre_spawn_hook(spawner):
    """Vérifie l'UUID dans la DB et applique les ressources."""
    user_uuid = spawner.user.name
    print(f"--- SPAWNING START FOR: {user_uuid} ---")

    # Chemin vers la DB montée dans le conteneur Hub
    db_path = "/mnt/db/dslab.db"

    if not os.path.exists(db_path):
        print(f"ERREUR: Base de données introuvable à {db_path}")
        raise Exception("Configuration système : Base de données absente.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT cpu, ram FROM user_requests WHERE user_uuid=? AND is_approved=1", (user_uuid,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise Exception(
            f"Accès refusé : L'UUID {user_uuid} n'est pas approuvé.")

    # A. Application des limites
    spawner.cpu_limit = float(row[0])
    spawner.mem_limit = row[1]

    # B. Gestion des Volumes (Personnel + Partagé)
    # Note : Utilisation de l'UID de lisa (1000) pour les permissions
    user_workdir = f"/home/lisa/workspaces/{user_uuid}"
    if not os.path.exists(user_workdir):
        os.makedirs(user_workdir, mode=0o755, exist_ok=True)

    spawner.volumes = {
        user_workdir: {"bind": "/home/jovyan/work", "mode": "Z"},
        "/opt/ds_shared_libs": {"bind": "/opt/shared", "mode": "ro"}
    }

    # C. Environnement
    spawner.environment = {
        "CHOWN_HOME": "yes",       # Active le chown au démarrage
        "CHOWN_HOME_OPTS": "-R",   # Récursif
        "NB_USER": "jovyan",       # L'utilisateur final après chown
        "NB_UID": "1000",
        "NB_GID": "100",
        "PYTHONPATH": "/opt/shared/venv/lib/python3.12/site-packages",
        "JUPYTERHUB_SERVICE_URL": "http://jupyterhub:8888/hub/api",
        "JUPYTERHUB_API_URL": "http://jupyterhub:8888/hub/api",
        "JUPYTERHUB_CLIENT_ID": f"jupyterhub-user-{user_uuid}",
        "JUPYTER_IP": "0.0.0.0"
    }

c.DockerSpawner.pre_spawn_hook = pre_spawn_hook

# --- 5. SERVICES : IDLE CULLER ---
c.JupyterHub.services = [
    {
        'name': 'cull-idle',
        'admin': True,
        'command': [
            'python3', '-m', 'jupyterhub_idle_culler',
            '--url=http://127.0.0.1:8888/hub/api',
            '--timeout=1800',
        ],
    }
]
