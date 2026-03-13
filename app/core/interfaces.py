from abc import ABC, abstractmethod
from typing import Optional

from app.core.entities import UserRequest


class UserRequestRepository(ABC):
    @abstractmethod
    def save(self, request: UserRequest) -> UserRequest:
        pass

    @abstractmethod
    def get_by_id(self, request_id: int) -> Optional[UserRequest]:
        pass

    @abstractmethod
    def list_all(self) -> list[UserRequest]:
        pass

    @abstractmethod
    def update_status(self, request_id: int, status: bool):
        pass

    @abstractmethod
    def get_by_uuid(self, user_uuid: str) -> Optional[UserRequest]:
        pass


class MailService(ABC):
    @abstractmethod
    def send_approval(self, to_email: str, user_uuid: str, url: str):
        pass
