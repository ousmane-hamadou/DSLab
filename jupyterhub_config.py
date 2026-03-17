import os
import socket
import sqlite3
from urllib.parse import parse_qs, unquote, urlparse

import netifaces
from jupyterhub.auth import DummyAuthenticator

c = get_config()

# --- 0. RÉCUPÉRATION RÉSEAU ---


def get_dynamic_network_info():
    info = {'ip': '127.0.0.1', 'gateway': '127.0.0.1'}
    try:
        gws = netifaces.gateways()
        if 'default' in gws and netifaces.AF_INET in gws['default']:
            info['gateway'] = gws['default'][netifaces.AF_INET][0]
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
c.JupyterHub.hub_ip = '0.0.0.0'
c.JupyterHub.hub_port = 8888
c.JupyterHub.hub_connect_ip = 'jupyterhub'

# Indispensable pour Ngrok/Traefik : fait confiance au Host envoyé par le proxy
c.JupyterHub.forwarded_host_header = 'X-Forwarded-Host'

# --- 2. SÉCURITÉ & TORNADO (CORRECTIF DES WARNINGS) ---
c.JupyterHub.bind_url = 'http://:8000'
c.JupyterHub.subdomain_host = ''  # Désactivé pour éviter les erreurs SSL wildcard
c.JupyterHub.base_url = '/'
c.JupyterHub.allowed_hostnames = set()

# Configuration adaptative des cookies
cookie_options = {
    'SameSite': 'Lax',
    'Secure': False
}

if "https" in str(c.JupyterHub.bind_url):
    cookie_options.update({'SameSite': 'None', 'Secure': True})

# On injecte les réglages dans tornado_settings au lieu de c.JupyterHub directement
c.JupyterHub.tornado_settings = {
    'headers': {
        'Content-Security-Policy': "frame-ancestors 'self' *",
        'Access-Control-Allow-Origin': '*'
    },
    'trust_x_forwarded': True,  # Correction de trust_x_forwarded_headers
    'cookie_options': cookie_options,
    'check_xsrf': False
}

# --- 3. AUTHENTIFICATION & RÔLES ---
admin_list = {'lisa'}
c.Authenticator.admin_users = admin_list

c.JupyterHub.load_roles = [
    {
        "name": "collaboration-access",
        "scopes": ["access:servers", "read:users", "read:users:name", "read:groups"],
        "services": ["jupyter_collaboration"],
    },
    {
        "name": "user-api",
        "scopes": ["self", "access:servers"],
        "users": list(admin_list)
    }
]


class MyAuthenticator(DummyAuthenticator):
    async def authenticate(self, handler, data=None):
        username = handler.get_argument("username", None)
        if not username:
            next_url = handler.get_argument("next", None)
            if next_url:
                decoded_next = unquote(next_url)
                params = parse_qs(urlparse(decoded_next).query)
                if 'username' in params:
                    username = params['username'][0]
                elif '/user/' in decoded_next:
                    parts = decoded_next.split('/')
                    username = parts[parts.index('user') + 1]

        if username:
            print(f"--- [AUTH SUCCESS] UUID : {username} ---", flush=True)
            return {"name": username}
        return None


c.JupyterHub.authenticator_class = MyAuthenticator
c.Authenticator.auto_login = True
c.JupyterHub.shutdown_on_logout = True

# --- 4. CONFIGURATION DU SPAWNER (PODMAN) ---
c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'
c.DockerSpawner.image = 'dslab-collab:latest'
c.DockerSpawner.client_kwargs = {'base_url': 'unix:///var/run/docker.sock'}

network_name = 'dslab-net'
c.DockerSpawner.network_name = network_name
c.DockerSpawner.hub_connect_url = 'http://jupyterhub:8888'
c.DockerSpawner.use_internal_ip = True

# Activation de la collaboration (RTC) dans les notebooks
c.DockerSpawner.args = [
    '--ip=0.0.0.0',
    '--port=8888',
    '--LabApp.collaborative=True',
    '--ContentsManager.allow_hidden=True'
]
c.JupyterHub.trusted_proxies = [
    network_info['ip'],
    network_info['gateway'],
    'traefik'
]
c.JupyterHub.redirect_to_server = True

c.DockerSpawner.extra_host_config = {"network_mode": network_name}
c.DockerSpawner.extra_create_kwargs = {'user': '0'}
c.DockerSpawner.remove = True
c.Spawner.start_timeout = 300
c.Spawner.http_timeout = 180

# --- 5. PRE-SPAWN HOOK (LIMITES & VOLUMES) ---


async def pre_spawn_hook(spawner):
    user_uuid = spawner.user.name
    db_path = "/mnt/db/dslab.db"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT cpu, ram FROM user_requests WHERE user_uuid=? AND is_approved=1", (user_uuid,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise Exception(f"Accès refusé : {user_uuid} non approuvé.")

    spawner.cpu_limit = float(row[0])
    spawner.mem_limit = row[1]

    user_workdir = f"/home/lisa/workspaces/{user_uuid}"
    os.makedirs(user_workdir, mode=0o755, exist_ok=True)

    spawner.volumes = {
        user_workdir: {"bind": "/home/jovyan/work", "mode": "Z"},
        "/opt/ds_shared_libs": {"bind": "/opt/shared", "mode": "ro"}
    }

    spawner.environment = {
        "JUPYTERHUB_SINGLEUSER_APP": "jupyter_server.serverapp.ServerApp",
        "PYTHONPATH": "/opt/shared/venv/lib/python3.12/site-packages",
        "NB_USER": "jovyan",
        "NB_UID": "1000",
        "NB_GID": "100",
        "CHOWN_HOME": "yes",
        "CHOWN_HOME_OPTS": "-R",
        "JUPYTER_IP": "0.0.0.0",
        "JUPYTERHUB_SERVICE_URL": "http://jupyterhub:8888/hub/api",
        "JUPYTERHUB_API_URL": "http://jupyterhub:8888/hub/api",
        "JUPYTERHUB_CLIENT_ID": f"jupyterhub-user-{user_uuid}",
    }

c.DockerSpawner.pre_spawn_hook = pre_spawn_hook

# --- 6. SERVICES ---
c.JupyterHub.services = [
    {
        'name': 'jupyter_collaboration',
        'api_token': os.environ.get('JUPYTERHUB_API_TOKEN', '3e3076d69391ac3a8ce9bec643f543d3865bf206e63677fdab4aec6857c60416'),
    },
    {
        'name': 'cull-idle',
        'admin': True,
        'command': ['python3', '-m', 'jupyterhub_idle_culler', '--timeout=1800'],
    }
]
