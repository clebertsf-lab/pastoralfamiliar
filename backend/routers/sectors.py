import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from lib.auth import COORD, SUB, get_current_user, require_roles
from lib.db import db
from models.sector import Sector, SectorIn, SectorOption
from models.user import MessageOut

router = APIRouter(prefix="/sectors", tags=["sectors"])
coord_only = require_roles(COORD)


@router.get("/options", response_model=List[SectorOption])
async def sector_options():
    """Public: names only, used by the self-signup form."""
    docs = await db.sectors.find({}, {"_id": 0, "id": 1, "name": 1}).sort("name", 1).to_list(500)
    return [SectorOption(**d) for d in docs]


@router.get("", response_model=List[Sector])
async def list_sectors(_: dict = Depends(get_current_user)):
    sectors = await db.sectors.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    users = await db.users.find(
        {"status": "active", "sector_ids.0": {"$exists": True}}, {"_id": 0, "sector_ids": 1, "role": 1, "name": 1}
    ).to_list(5000)
    out = []
    for s in sectors:
        in_sector = [u for u in users if s["id"] in u.get("sector_ids", [])]
        out.append(
            Sector(
                **s,
                member_count=len(in_sector),
                leaders=[u["name"] for u in in_sector if u["role"] in (COORD, SUB)],
            )
        )
    return out


@router.post("", response_model=Sector, status_code=201)
async def create_sector(body: SectorIn, _: dict = Depends(coord_only)):
    doc = {"id": str(uuid.uuid4()), "name": body.name.strip(), "description": body.description.strip()}
    await db.sectors.insert_one(doc)
    return Sector(**doc)


@router.put("/{sector_id}", response_model=Sector)
async def update_sector(sector_id: str, body: SectorIn, _: dict = Depends(coord_only)):
    res = await db.sectors.update_one(
        {"id": sector_id}, {"$set": {"name": body.name.strip(), "description": body.description.strip()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Setor não encontrado")
    doc = await db.sectors.find_one({"id": sector_id}, {"_id": 0})
    return Sector(**doc)


@router.delete("/{sector_id}", response_model=MessageOut)
async def delete_sector(sector_id: str, _: dict = Depends(coord_only)):
    res = await db.sectors.delete_one({"id": sector_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Setor não encontrado")
    await db.users.update_many({"sector_ids": sector_id}, {"$pull": {"sector_ids": sector_id}})
    await db.events.update_many({"sector_id": sector_id}, {"$set": {"sector_id": None}})
    return MessageOut(message="Setor removido")
