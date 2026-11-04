from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class EventRoleIn(BaseModel):
    id: Optional[str] = None
    name: str = Field(min_length=1, max_length=60)
    slots: Optional[int] = Field(default=None, ge=1, le=500)


class EventRoleOut(BaseModel):
    id: str
    name: str
    slots: Optional[int] = None
    taken: int = 0


class EventIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(default="", pattern=r"^(\d{2}:\d{2})?$")
    location: str = Field(default="", max_length=120)
    sector_id: Optional[str] = None
    escala_open: bool = True
    slots: Optional[int] = Field(default=None, ge=1, le=500)
    roles: List[EventRoleIn] = Field(default=[], max_length=30)


class Helper(BaseModel):
    user_id: str
    name: str
    phone: Optional[str] = None
    role_id: Optional[str] = None
    role_name: Optional[str] = None


class EventOut(BaseModel):
    id: str
    title: str
    description: str = ""
    date: str
    time: str = ""
    location: str = ""
    sector_id: Optional[str] = None
    sector_name: Optional[str] = None
    escala_open: bool
    slots: Optional[int] = None
    roles: List[EventRoleOut] = []
    helpers: List[Helper] = []
    declined: List[Helper] = []  # leaders only
    pending: List[Helper] = []  # leaders only: eligible members who did not answer
    declined_count: int = 0
    attendance: List[str] = []  # leaders only: user ids marked present
    my_response: Optional[Literal["going", "not_going"]] = None
    my_role_id: Optional[str] = None
    can_respond: bool = False
    can_manage: bool = False
    can_mark_attendance: bool = False
    is_past: bool = False
    created_at: Optional[datetime] = None


class RsvpIn(BaseModel):
    response: Literal["going", "not_going"]
    role_id: Optional[str] = None


class AttendanceIn(BaseModel):
    present_user_ids: List[str] = Field(default=[], max_length=2000)
