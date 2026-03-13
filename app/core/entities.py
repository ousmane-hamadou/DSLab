import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserRequest:
    email: str
    project_desc: str
    cpu: int
    ram: str
    id: Optional[int] = None
    user_uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_approved: bool = False
