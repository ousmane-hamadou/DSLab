import logging
from typing import List, Optional

from sqlalchemy import Column, Double, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.core.entities import UserRequest

logger = logging.getLogger("dslab.infrastructure.database")

# Définition de la base pour SQLAlchemy
Base = declarative_base()

# Modèle de données (Table SQL)


class UserRequestModel(Base):
    __tablename__ = "user_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_approved: Mapped[bool] = mapped_column(default=False)
    # Notre identifiant UUID
    user_uuid = Column(String, unique=True, index=True)
    email = Column(String)
    project_desc = Column(String)
    cpu = Column(Integer)
    ram = Column(String)


class AdminModel(Base):
    """
    Modèle SQLAlchemy pour la gestion des administrateurs de DSLab.
    """
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)

    def __repr__(self):
        return f"<Admin(username='{self.username}')>"


class SqlAlchemyRepository:
    def __init__(self, db_session: Session):
        self.db = db_session

    def save(self, entity: UserRequest) -> UserRequest:
        """Transforme l'entité en modèle SQL et l'enregistre."""
        model = UserRequestModel(
            user_uuid=entity.user_uuid,
            email=entity.email,
            project_desc=entity.project_desc,
            cpu=entity.cpu,
            ram=entity.ram,
            is_approved=entity.is_approved
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        entity.id = model.id
        return entity

    def get_by_uuid(self, user_uuid: str):
        return self.db.query(UserRequestModel).filter(
            UserRequestModel.user_uuid == user_uuid
        ).first()

    def get_by_id(self, request_id: int) -> Optional[UserRequest]:
        """Récupère en DB et transforme en entité Core."""
        model = self.db.query(UserRequestModel).filter(
            UserRequestModel.id == request_id).first()
        if not model:
            return None
        return self._to_entity(model)

    def update_status(self, request_id: int, status: bool):
        """Met à jour le statut d'approbation."""
        model = self.db.query(UserRequestModel).filter(
            UserRequestModel.id == request_id).first()
        if model:
            model.is_approved = status
            self.db.commit()

    def list_all(self) -> List[UserRequest]:
        """Liste toutes les demandes."""
        models = self.db.query(UserRequestModel).all()
        return [self._to_entity(m) for m in models]

    def _to_entity(self, model: UserRequestModel) -> UserRequest:
        """Transforme le modèle SQL en entité métier."""
        return UserRequest(
            email=str(model.email),
            project_desc=str(model.project_desc),
            cpu=int(str(model.cpu)),
            ram=str(model.ram),
            id=model.id,
            user_uuid=str(model.user_uuid),
            is_approved=model.is_approved
        )


# Configuration de la connexion
DATABASE_URL = "sqlite:////app/data/dslab.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    Initialise la base de données :
    1. Crée toutes les tables définies dans les modèles.
    2. Vérifie si un administrateur existe.
    3. Sinon, crée le compte 'admin' par défaut avec mot de passe haché.
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        from app.core.security import hash_password
        admin = db.query(AdminModel).filter(
            AdminModel.username == "admin").first()

        if not admin:
            logger.info(
                "Initialisation : Création du compte admin (Argon2)...")
            db.add(AdminModel(username="admin", password=hash_password("admin")))
            db.commit()

    except Exception as e:
        logger.error(f"Erreur init_db : {e}")
    finally:
        db.close()
