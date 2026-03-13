from fastapi.responses import RedirectResponse
from fastapi import Depends, HTTPException, status
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import jwt
from fastapi import (Cookie, Depends, FastAPI, Form, HTTPException, Request,
                     Response)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.security import ALGORITHM, SECRET_KEY
from app.core.use_cases import ManageAdmins, ManageUserRequest
from app.infrastructure.database import (SessionLocal, SqlAlchemyRepository,
                                         init_db)
from app.infrastructure.mailservice import SmtpMailService

logger = logging.getLogger("dslab.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Démarrage de DSLab : Initialisation de la base de données...")

    init_db()

    yield
    logger.info("Fermeture de DSLab : Nettoyage des ressources...")


async def get_current_admin(access_token: Optional[str] = Cookie(None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Non connecté")
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Session invalide")

# Initialisation de FastAPI et des templates

app = FastAPI(title="DSLab", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user_service(db: Session = Depends(get_db)):
    """
    Injecte les dépendances nécessaires dans ManageUserRequest.
    - Repository : pour l'accès à SQLite.
    - MailService : pour l'envoi des notifications SMTP.
    - NGROK_URL : pour générer les liens de session.
    """
    # 1. Récupération de l'URL du tunnel depuis l'environnement
    ngrok_url = os.getenv("NGROK_URL", "http://localhost:8000")

    # 2. Initialisation des composants d'infrastructure
    repository = SqlAlchemyRepository(db)
    mail_service = SmtpMailService()

    # 3. Retourne le Use Case configuré
    return ManageUserRequest(
        repository=repository,
        mail_service=mail_service,
        ngrok_url=ngrok_url
    )

# --- ROUTES UTILISATEURS ---


@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Affiche la nouvelle page de présentation."""
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/request", response_class=HTMLResponse)
async def request_form(request: Request):
    """Affiche le formulaire de demande (ancien index)."""
    return templates.TemplateResponse("form.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    admin_service = ManageAdmins(db)
    token = admin_service.authenticate(username, password)

    if not token:
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    response = RedirectResponse(url="/admin", status_code=303)
    # Sécurisation du cookie pour le tunnel ngrok
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,   # Obligatoire pour HTTPS (ngrok)
        samesite="lax"
    )
    return response


@app.post("/submit", response_class=HTMLResponse)
async def submit_request(
    request: Request,
    email: str = Form(...),
    project_desc: str = Form(...),
    cpu: int = Form(...),
    ram: str = Form(...),
    service: ManageUserRequest = Depends(get_user_service)
):
    try:
        # Enregistrement via le Use Case (qui utilise Argon2 et SQLite)
        service.submit(email=email, project_desc=project_desc,
                       cpu=cpu, ram=ram)

        # On renvoie la page de succès
        return templates.TemplateResponse("submitted.html", {"request": request})
    except Exception as e:
        # En cas d'erreur, on peut renvoyer vers une page d'erreur ou lever une exception
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de l'envoi : {e}")

# --- ROUTES ADMIN ---


@app.get("/admin")
async def admin_panel(
    request: Request,
    user: str = Depends(get_current_admin),  # Protection
    service: ManageUserRequest = Depends(get_user_service)
):
    requests = service.list_requests()
    return templates.TemplateResponse("admin.html", {"request": request, "requests": requests, "admin_user": user})


@app.post("/admin/approve/{request_id}")
async def approve_request(
    request_id: int,
    service: ManageUserRequest = Depends(get_user_service)
):
    """Approuve une demande et déclenche l'envoi de l'email avec l'URL de session."""

    updated_req = service.approve(request_id)
    if not updated_req:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    return {"status": "success"}


@app.post("/admin/add")
async def create_new_admin(
    new_username: str = Form(...),
    new_password: str = Form(...),
    current_user: str = Depends(get_current_admin),  # Protection
    db: Session = Depends(get_db)
):
    admin_service = ManageAdmins(db)
    try:
        admin_service.add_admin(new_username, new_password)
        return RedirectResponse(url="/admin", status_code=303)
    except Exception:
        raise HTTPException(
            status_code=400, detail="Erreur lors de la création")


@app.get("/logout")
async def logout(response: Response):
    # On crée une redirection vers l'accueil
    redirect = RedirectResponse(url="/", status_code=303)

    # On supprime le cookie contenant le token (nommé 'access_token' par convention)
    # Assure-toi que le nom correspond à celui utilisé lors du login
    redirect.delete_cookie(
        key="access_token",
        path="/",        # Important pour supprimer le cookie sur tout le domaine
        httponly=True,   # Sécurité contre XSS
        samesite="lax"
    )

    print("Déconnexion réussie : Cookie supprimé.")
    return redirect

# --- ROUTE DE SESSION (POINT D'ENTRÉE NGROK) ---


@app.get("/session/{user_uuid}")
async def user_session_access(
    user_uuid: str,
    service: ManageUserRequest = Depends(get_user_service)
):
    validated_req = service.get_valid_request(user_uuid)

    if not validated_req:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé. Lien invalide ou demande non approuvée."
        )

    # On récupère l'URL publique (ngrok) configurée dans le service
    # Exemple : https://abcd-123.ngrok-free.app
    public_url = service.ngrok_url

    # Redirection via le tunnel public.
    # Traefik verra passer "/hub" et l'enverra au conteneur JupyterHub.
    # hub_url = f"{public_url}/hub/spawn?username={user_uuid}"
    # next_url = "/hub/spawn"
    # hub_url = f"{public_url}/hub/login?username={user_uuid}&next={next_url}"
    hub_url = f"{public_url}/hub/login?username={user_uuid}"
    return RedirectResponse(url=hub_url)
