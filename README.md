# DSLab - Infrastructure de Calcul pour Étudiants

Ce projet déploie une infrastructure complète de gestion de travaux pratiques basée sur **JupyterHub**, **FastAPI** et **Traefik**, le tout orchestré par **Podman** sur un environnement Rootless (Fedora).

## 🚀 Composants de l'Infrastructure

L'architecture repose sur trois conteneurs principaux :

- **Traefik** : Reverse proxy et gestionnaire de points d'entrée.
- **DSLab Web** : Interface d'administration et API (FastAPI) pour la gestion des requêtes.
- **JupyterHub** : Gestionnaire de sessions notebooks pour les étudiants, utilisant `DockerSpawner`.

---

## 🛠 Prérequis Serveur (Fedora/RHEL)

Avant le déploiement, assurez-vous que les composants suivants sont installés sur l'hôte :

1. **Podman & Podman Compose** :

   ```bash
   sudo dnf install podman podman-compose sqlite
   ```

2. **Activer le Socket Podman (Rootless)** :

   ```bash
   systemctl --user enable --now podman.socket
   export XDG_RUNTIME_DIR=/run/user/$(id -u)
   ```

3. **SELinux & Permissions** (Nécessaire pour l'accès au socket) :

   ```bash
   sudo setsebool -P container_manage_cgroup on
   chmod 666 ${XDG_RUNTIME_DIR}/podman/podman.sock
   ```

---

## 🌐 Configuration de Ngrok

Pour exposer votre infrastructure locale sur le web, utilisez **Ngrok**.

1. **Installation** :

   ```bash
   sudo dnf install ngrok
   ```

2. **Authentification** :

   ```bash
   ngrok config add-authtoken <VOTRE_TOKEN>
   ```

3. **Lancement** :
   Exposez le port de Traefik (8080 dans notre configuration) :

   ```bash
   ngrok http 8080
   ```

   _Note : Copiez l'URL fournie (ex: `https://votre-id.ngrok-free.dev`) pour la configurer dans l'interface d'administration._

---

## 📁 Création des Volumes et Persistance

### Identification du matériel

Avant toute chose, identifiez le nom du disque à formater (ex: `/dev/sdb`).

```bash
lsblk

# La première étape consiste à transformer le disque brut en un Physical Volume que LVM peut manipuler.
sudo pvcreate /dev/sdb

# On regroupe un ou plusieurs volumes physiques dans un "pool" de stockage global.
sudo vgcreate vg_dslab /dev/sdb
```

### Création et Formatage des Volumes Logiques

```bash
# 1. Créer le volume pour l'espace partagé (ex: 20 Go)
sudo lvcreate -L 20G -n lv_shared vg_dslab

# 2. Créer le volume pour les workspaces (ex: le reste du disque)
sudo lvcreate -l 100%FREE -n lv_workspaces vg_dslab

# 3. Formater en XFS (Recommandé sur Fedora pour les quotas)
sudo mkfs.xfs /dev/vg_dslab/lv_shared
sudo mkfs.xfs /dev/vg_dslab/lv_workspaces
```

### Montage Permanent (/etc/fstab)

```bash
# Créer les points de montage
sudo mkdir -p /opt/ds_shared_libs
sudo mkdir -p /home/lisa/workspaces

# Ajouter au fichier fstab (ajoute ces lignes à la fin du fichier)
# Utilise 'sudo nano /etc/fstab'
/dev/mapper/vg_dslab-lv_shared      /opt/ds_shared_libs     xfs     defaults        0 0
/dev/mapper/vg_dslab-lv_workspaces  /home/lisa/workspaces xfs   defaults,prjquota  0 0

# Monter tout immédiatement
sudo mount -a

# Vérifier que le montage a bien pris l'option prjquota
mount | grep workspaces

# Si tu vois 'prjquota', tu peux maintenant utiliser l'option
# --storage-opt size=80G dans Podman sereinement.
```

### Correction des Permissions & SELinux

```bash
# Permissions pour ton utilisateur
sudo chown -R $USER:$USER /opt/ds_shared_libs
sudo chown -R $USER:$USER /home/lisa/workspaces

# SELinux : Autoriser Podman à lire/écrire sur ces nouveaux montages
sudo semanage fcontext -a -t container_file_t "/opt/ds_shared_libs(/.*)?"
sudo semanage fcontext -a -t container_file_t "/home/lisa/workspaces(/.*)?"
sudo restorecon -Rv /opt/ds_shared_libs
sudo restorecon -Rv /home/lisa/workspaces
```

### Création de l'espace de stockage sur l'hôte

```bash
# Création du dossier
sudo mkdir -p /opt/ds_shared_libs

# Donner la propriété à ton utilisateur (lisa)
# pour que tu puisses installer des paquets sans sudo
sudo chown -R $USER:$USER /opt/ds_shared_libs

# Appliquer le contexte SELinux pour autoriser Podman à lire ce dossier
sudo semanage fcontext -a -t container_file_t "/opt/ds_shared_libs(/.*)?"
sudo restorecon -Rv /opt/ds_shared_libs
```

### Initialisation de l'environnement Python Partagé

```bash
# Installation de venv si nécessaire
python3 -m venv /opt/ds_shared_libs/venv

# Activation de l'environnement pour installer les paquets
source /opt/ds_shared_libs/venv/bin/activate

# Mise à jour de pip et installation des paquets lourds
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install jax[cpu] tensorflow-cpu scikit-learn pandas matplotlib seaborn

# Désactivation
deactivate
```

Les données sont stockées sur l'hôte dans `/home/lisa/DSLab` pour assurer la persistance entre les redémarrages.

```bash
# Créer le répertoire de base
mkdir -p /home/lisa/DSLab

# Assigner les droits SELinux pour les conteneurs
chcon -Rt container_file_t /home/lisa/DSLab
```

<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->
