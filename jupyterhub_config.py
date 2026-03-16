import os
import socket
import sqlite3
from urllib.parse import parse_qs, unquote, urlparse

import netifaces
from jupyterhub.auth import DummyAuthenticator

c = get_config()

# Récupérer dynamiquement l'IP interne du conteneur JupyterHub


def get_dynamic_network_info():
    """Récupère l'IP du Hub et la Gateway du réseau Podman."""
    info = {'ip': '127.0.0.1', 'gateway': '127.0.0.1'}
    try:
        # 1. Obtenir l'IP de la Gateway par défaut (le bridge Podman)
        gws = netifaces.gateways()
        if 'default' in gws and netifaces.AF_INET in gws['default']:
            info['gateway'] = gws['default'][netifaces.AF_INET][0]

        # 2. Obtenir l'IP interne du Hub
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 1))
        info['ip'] = s.getsockname()[0]
        s.close()
    except Exception as e:
        print(f"Erreur détection réseau : {e}")
    return info


network_info = get_dynamic_network_info()


# --- 1. CONFIGURATION RÉSEAU GÉNÉRALE ---
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000


# Port pour l'API interne (Communication Hub <-> Notebooks)
c.JupyterHub.hub_ip = '0.0.0.0'
c.JupyterHub.hub_port = 8888

# On utilise l'alias défini dans docker-compose au lieu d'une IP fixe
c.JupyterHub.hub_connect_ip = 'jupyterhub'

# --- 2. CONFIGURATION DE LA COLLABORATION (TORNADO) ---
c.JupyterHub.allow_origin = '*'
c.JupyterHub.bind_url = 'http://:8000'
c.JupyterHub.trust_x_forwarded_headers = True
c.JupyterHub.subdomain_host = ''
c.JupyterHub.base_url = '/'

# --- AJUSTEMENT COLLABORATION & API ---

admin_list = {'lisa'}
c.Authenticator.admin_users = admin_list

c.JupyterHub.load_roles = [
    {
        "name": "collaboration-access",
        "scopes": ["access:servers", "read:users", "read:users:name", "read:groups"],
        "services": ["jupyter_collaboration"],
    },
    {
        "name": "user",
        "scopes": ["self", "access:servers"],
        "users": list(admin_list)
    }
]

c.JupyterHub.tornado_settings = {
    'headers': {
        'Content-Security-Policy': "frame-ancestors 'self' *",
        'Access-Control-Allow-Origin': '*'
    },
    'cookie_options': {
        'SameSite': 'None',
        'Secure': True
    },
    'check_xsrf': False
}

# --- 3. AUTHENTIFICATION CUSTOM ---


class MyAuthenticator(DummyAuthenticator):
    async def authenticate(self, handler, data=None):
        # 1. Tentative directe : ?username=...
        username = handler.get_argument("username", None)

        # 2. Si non trouvé, on fouille dans le paramètre 'next'
        if not username:
            next_url = handler.get_argument("next", None)
            if next_url:
                decoded_next = unquote(next_url)
                parsed_next = urlparse(decoded_next)
                params = parse_qs(parsed_next.query)

                if 'username' in params:
                    username = params['username'][0]
                elif '/user/' in decoded_next:
                    parts = decoded_next.split('/')
                    username = parts[parts.index('user') + 1]

        if username:
            print(f"--- [AUTH SUCCESS] UUID détecté : {username} ---")
            return {"name": username}

        print("--- [AUTH FAILURE] Aucun UUID trouvé dans l'URL ---")
        return None


c.JupyterHub.authenticator_class = MyAuthenticator
c.Authenticator.auto_login = True
c.Authenticator.allow_all = True
c.Authenticator.any_allow_config = True
c.Authenticator.allow_existing_users = True
c.JupyterHub.allow_named_servers = False
c.DockerSpawner.args.extend([
    '--LabApp.collaborative=True',
    '--ContentsManager.allow_hidden=True'
])
c.JupyterHub.trusted_proxies = [
    network_info['ip'],
    network_info['gateway'],
    'traefik'
]
c.JupyterHub.redirect_to_server = True
# --- 4. CONFIGURATION DU SPAWNER (PODMAN / DOCKERSPAWNER) ---
c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'
c.DockerSpawner.image = 'dslab-collab:latest'

# Socket Podman (Standard Fedora Rootless)
c.DockerSpawner.client_kwargs = {
    'base_url': 'unix:///var/run/docker.sock'
}

# Configuration du réseau dslab-net
network_name = 'dslab-net'
c.DockerSpawner.network_name = network_name
c.DockerSpawner.hub_connect_url = 'http://jupyterhub:8888/hub/api'
c.DockerSpawner.args = [
    '--ip=0.0.0.0',
    '--port=8888',
    '--LabApp.collaborative=True'
]
c.DockerSpawner.use_internal_ip = True

# Options spécifiques pour Podman et la stabilité
c.DockerSpawner.extra_host_config = {
    "network_mode": network_name,
}
c.DockerSpawner.extra_create_kwargs = {'user': '0'}
c.DockerSpawner.remove = True
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
    spawner.environment.update({
        "JUPYTERHUB_SINGLEUSER_APP": "jupyter_server.serverapp.ServerApp",
    })

c.DockerSpawner.pre_spawn_hook = pre_spawn_hook
c.JupyterHub.shutdown_on_logout = True
# --- 5. SERVICES : IDLE CULLER ---
c.JupyterHub.services = [
    {
        'name': 'jupyter_collaboration',
        'api_token': os.environ.get('JUPYTERHUB_API_TOKEN', '3e3076d69391ac3a8ce9bec643f543d3865bf206e63677fdab4aec6857c60416'),
    },
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
