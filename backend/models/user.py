from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Role = Literal["coordenador", "subcoordenador", "membro"]
Status = Literal["active", "pending"]
USERNAME_PATTERN = r"^[a-zA-Z0-9._-]{3,30}$"


class UserPublic(BaseModel):
    id: str
    username: str
    name: str
    phone: str = ""
    notes: Optional[str] = None
    role: Role
    sector_ids: List[str] = []
    status: Status
    created_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    served_count: int = 0
    last_served: Optional[str] = None  # YYYY-MM-DD of the last event with confirmed attendance


class LoginIn(BaseModel):
    username: str
    password: str


class SignupIn(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=6, max_length=100)
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(default="", max_length=30)
    sector_ids: List[str] = []
    notes: str = Field(default="", max_length=1000)


class MemberCreate(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=6, max_length=100)
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(default="", max_length=30)
    notes: str = Field(default="", max_length=1000)
    role: Role = "membro"
    sector_ids: List[str] = []


class MemberUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(default="", max_length=30)
    notes: str = Field(default="", max_length=1000)
    role: Role = "membro"
    sector_ids: List[str] = []
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)


class HistoryItem(BaseModel):
    event_id: str
    title: str
    date: str
    role_name: Optional[str] = None


class MessageOut(BaseModel):
    message: str
