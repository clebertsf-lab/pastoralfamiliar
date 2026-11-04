from typing import List

from pydantic import BaseModel, Field


class SectorIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=300)


class SectorOption(BaseModel):
    id: str
    name: str


class Sector(BaseModel):
    id: str
    name: str
    description: str = ""
    member_count: int = 0
    leaders: List[str] = []
