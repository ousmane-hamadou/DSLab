from typing import List, Optional

from app.core.entities import UserRequest
from app.core.security import (create_access_token, hash_password,
                               verify_password)
from app.infrastructure.database import AdminModel


class ManageUserRequest:
    def __init__(self, repository, mail_service, ngrok_url: str):
        """
        Initialise le cas d'utilisation avec ses dépendances (Inversion de contrôle).

        :param repository: L'interface d'accès aux données (Infrastructure)
        :param mail_service: L'interface d'envoi de notifications (Infrastructure)
        :param ngrok_url: URL publique (ex: https://nom-du-tunnel.ngrok-free.app)
        """
        self.repository = repository
        self.mail_service = mail_service
        self.ngrok_url = ngrok_url.strip("/")

    def submit(self, email: str, project_desc: str, cpu: int, ram: str) -> UserRequest:
        """
        Traite la soumission d'une nouvelle demande.
        """

        request = UserRequest(
            email=email,
            project_desc=project_desc,
            cpu=cpu,
            ram=ram
        )
        return self.repository.save(request)

    def approve(self, request_id: int) -> Optional[UserRequest]:
        """
        Approuve une demande et déclenche l'envoi de l'URL via le tunnel ngrok.
        """

        request = self.repository.get_by_id(request_id)
        if not request:
            return None

        self.repository.update_status(request_id, True)

        return request

    def list_requests(self, approved_only: bool = False) -> List[UserRequest]:
        """
        Liste les demandes selon leur statut.
        """
        all_requests = self.repository.list_all()
        if approved_only:
            return [r for r in all_requests if r.is_approved]
        return all_requests

        return self.repository.list_all()

    def get_valid_request(self, user_uuid: str) -> Optional[UserRequest]:
        """
        Vérifie en base si l'UUID existe et si la demande est approuvée.
        Retourne l'objet ou None si invalide.
        """
        req = self.repository.get_by_uuid(user_uuid)
        if req and req.is_approved:
            return req
        return None


class ManageAdmins:
    def __init__(self, db_session):
        self.db = db_session

    def authenticate(self, username, password) -> Optional[str]:
        """Vérifie les identifiants et retourne un token JWT si valide."""
        from app.infrastructure.database import AdminModel
        admin = self.db.query(AdminModel).filter(
            AdminModel.username == username).first()

        if admin and verify_password(password, admin.password):
            return create_access_token({"sub": username})
        return None

    def add_admin(self, username, password):
        """Hache le mot de passe et enregistre le nouvel admin."""
        from app.infrastructure.database import AdminModel
        hashed = hash_password(password)
        new_admin = AdminModel(username=username, password=hashed)
        self.db.add(new_admin)
        self.db.commit()
        return new_admin
