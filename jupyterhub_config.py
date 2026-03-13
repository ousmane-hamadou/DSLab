import os
import shutil
import sqlite3

import netifaces
from jupyterhub.auth import DummyAuthenticator

c = get_config()

docker_gw = netifaces.gateways()['default'][netifaces.AF_INET][0]

c.JupyterHub.hub_connect_ip = docker_gw
# OU plus simplement si tes conteneurs sont sur le même network bridge :
c.JupyterHub.hub_ip = '0.0.0.0'
c.DockerSpawner.hub_connect_ip_from_env = 'JUPYTERHUB_SERVICE_HOST'


# --- 1. CONFIGURATION RÉSEAU ---
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000
c.JupyterHub.admin_access = True

# --- 2. AUTHENTIFICATION ---


class MyAuthenticator(DummyAuthenticator):
    async def authenticate(self, handler, data):
        # On essaie de récupérer le username dans l'URL (?username=...)
        username = handler.get_argument("username", None)
        if username:
            return {"name": username}
        # Sinon on laisse le comportement par défaut (formulaire)
        return await super().authenticate(handler, data)


# --- NOUVEAUX RÉGLAGES D'AUTORISATION ---
# Autorise explicitement tous les utilisateurs authentifiés
c.JupyterHub.authenticator_class = MyAuthenticator
c.Authenticator.auto_login = True
c.Authenticator.allow_all = True
# Masque l'avertissement de sécurité
c.Authenticator.any_allow_config = True
c.Authenticator.allow_existing_users = True

# Optionnel : Si l'UUID ne passe toujours pas, force la création de l'utilisateur
c.Authenticator.admin_users = {'lisa'}

c.JupyterHub.allow_named_servers = True
c.Authenticator.create_system_users = False

# --- 3. CONFIGURATION DU SPAWNER (DOCKERSPAWNER + PODMAN) ---
c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'
c.DockerSpawner.remove = True
# Image utilisée pour les sessions de Data Science
c.DockerSpawner.image = 'quay.io/jupyter/datascience-notebook:latest'
c.Spawner.start_timeout = 300
c.Spawner.http_timeout = 120
# Pointage vers le socket Podman de l'utilisateur (Fedora)
runtime_dir = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
c.DockerSpawner.client_kwargs = {
    'base_url': 'unix:///var/run/docker.sock'
}

# Configuration réseau du conteneur
c.DockerSpawner.network_name = 'bridge'
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.remove = True  # Supprime le conteneur à l'arrêt pour libérer la RAM

# --- 4. HOOK DE PRÉ-LANCEMENT (DYNAMIQUE) ---


async def pre_spawn_hook(spawner):
    """
    S'exécute avant le lancement. 
    Vérifie l'UUID et applique les ressources (CPU/RAM/Stockage).
    """
    user_uuid = spawner.user.name  # Le username récupéré est l'UUID
    print(f"--- SPAWNING START FOR: {user_uuid} ---")
    db_path = "/mnt/db/dslab.db"

    # --- Connexion DB & Vérification ---
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT cpu, ram FROM user_requests WHERE user_uuid=? AND is_approved=1", (user_uuid,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise Exception(
            f"Accès refusé : L'UUID {user_uuid} n'est pas approuvé ou inexistant.")

    # --- A. Ressources Dynamiques (CPU/RAM) ---
    spawner.cpu_limit = float(row[0])
    spawner.mem_limit = row[1]

    # --- B. Isolation Racine 80G (XFS Project Quota) ---
    spawner.extra_host_config = {
        "storage_opt": {"size": "1G"}
    }

    # --- C. Gestion des Volumes (Personnel + Partagé) ---
    user_workdir = f"/home/ousmaneh/workspaces/{user_uuid}"
    if not os.path.exists(user_workdir):
        os.makedirs(user_workdir, mode=0o755)

    spawner.volumes = {
        # Workspace UUID (Flag :Z pour SELinux Fedora)
        user_workdir: {"bind": "/home/jovyan/work", "mode": "Z"},
        # Librairies partagées (Lecture Seule)
        "/opt/ds_shared_libs": {"bind": "/opt/shared", "mode": "ro"}
    }

    # --- D. Injection du PYTHONPATH (Utilisation des libs partagées) ---
    spawner.environment = {
        "PYTHONPATH": "/opt/shared/venv/lib/python3.12/site-packages"
    }

c.JupyterHub.hub_ip = '0.0.0.0'
c.JupyterHub.hub_port = 8081

# Définit l'adresse que les services (comme le culler) doivent utiliser
c.JupyterHub.hub_connect_ip = '127.0.0.1'

c.DockerSpawner.pre_spawn_hook = pre_spawn_hook

# --- 5. SERVICES : IDLE CULLER (TIMEOUTS) ---
# Installe avec : pip install jupyterhub-idle-culler
c.JupyterHub.services = [
    {
        'name': 'cull-idle',
        'admin': True,
        'command': [
            'python3', '-m', 'jupyterhub_idle_culler',
            '--url=http://127.0.0.1:8081/hub/api',
            '--timeout=1800',      # 30 min d'inactivité
            '--cull-every=60',     # Vérification chaque minute
        ],
    }
]
