import uuid
from datetime import datetime, timezone
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException

from lib.auth import COORD, MEMBER, SUB, hash_password, member_scope, require_roles
from lib.db import db
from lib.stats import served_stats, to_public
from models.user import HistoryItem, MemberCreate, MemberUpdate, MessageOut, UserPublic

router = APIRouter(prefix="/members", tags=["members"])
leaders = require_roles(COORD, SUB)


async def load_scoped(principal: dict, member_id: str) -> dict:
    """Fetch a member only if the principal may manage it; otherwise 404."""
    doc = await db.users.find_one({"id": member_id, **member_scope(principal)})
    if not doc:
        raise HTTPException(status_code=404, detail="Membro não encontrado")
    return doc


async def valid_sectors(sector_ids: list[str]) -> list[str]:
    ids = list(dict.fromkeys(sector_ids))
    if not ids:
        return []
    if await db.sectors.count_documents({"id": {"$in": ids}}) != len(ids):
        raise HTTPException(status_code=400, detail="Setor inválido")
    return ids


async def one(doc: dict) -> UserPublic:
    return to_public(doc, await served_stats([doc["id"]]))


@router.get("", response_model=List[UserPublic])
async def list_members(status: Literal["active", "pending"] = "active", principal: dict = Depends(leaders)):
    docs = await db.users.find({**member_scope(principal), "status": status}).sort("name", 1).to_list(2000)
    stats = await served_stats([d["id"] for d in docs])
    return [to_public(d, stats) for d in docs]


@router.get("/{member_id}/history", response_model=List[HistoryItem])
async def member_history(member_id: str, principal: dict = Depends(leaders)):
    await load_scoped(principal, member_id)
    rows = await db.attendance.find({"user_id": member_id}).sort("event_date", -1).to_list(500)
    ids = [r["event_id"] for r in rows]
    events = {e["id"]: e for e in await db.events.find({"id": {"$in": ids}}, {"_id": 0}).to_list(500)}
    rsvps = {
        r["event_id"]: r.get("role_id")
        for r in await db.rsvps.find({"user_id": member_id, "event_id": {"$in": ids}}).to_list(500)
    }
    out = []
    for r in rows:
        ev = events.get(r["event_id"])
        if not ev:
            continue
        role_name = next((x["name"] for x in ev.get("roles", []) if x["id"] == rsvps.get(ev["id"])), None)
        out.append(HistoryItem(event_id=ev["id"], title=ev["title"], date=ev["date"], role_name=role_name))
    return out


@router.post("", response_model=UserPublic, status_code=201)
async def create_member(body: MemberCreate, principal: dict = Depends(leaders)):
    username = body.username.strip().lower()
    if await db.users.find_one({"username": username}):
        raise HTTPException(status_code=409, detail="Este usuário já está em uso")
    if principal["role"] == SUB:
        own = principal.get("sector_ids") or []
        role = MEMBER
        sector_ids = [s for s in dict.fromkeys(body.sector_ids) if s in own] or list(own)
    else:
        role, sector_ids = body.role, await valid_sectors(body.sector_ids)
    doc = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": hash_password(body.password),
        "name": body.name.strip(),
        "phone": body.phone.strip(),
        "notes": body.notes.strip(),
        "role": role,
        "sector_ids": sector_ids,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(doc)
    return to_public(doc)


@router.put("/{member_id}", response_model=UserPublic)
async def update_member(member_id: str, body: MemberUpdate, principal: dict = Depends(leaders)):
    target = await load_scoped(principal, member_id)
    update: dict = {"name": body.name.strip(), "phone": body.phone.strip(), "notes": body.notes.strip()}
    if principal["role"] == SUB:
        if target["role"] != MEMBER and target["id"] != principal["id"]:
            raise HTTPException(status_code=403, detail="Você só pode editar membros dos seus setores")
        if target["id"] != principal["id"]:
            own = principal.get("sector_ids") or []
            outside = [s for s in target.get("sector_ids", []) if s not in own]
            inside = [s for s in dict.fromkeys(body.sector_ids) if s in own]
            update["sector_ids"] = outside + inside
    else:
        if target["id"] == principal["id"] and body.role != COORD:
            raise HTTPException(status_code=400, detail="Você não pode remover seu próprio papel de coordenador")
        update["role"] = body.role
        update["sector_ids"] = await valid_sectors(body.sector_ids)
    if body.password:
        update["password_hash"] = hash_password(body.password)
    await db.users.update_one({"id": member_id}, {"$set": update})
    return await one({**target, **update})


@router.post("/{member_id}/approve", response_model=UserPublic)
async def approve_member(member_id: str, principal: dict = Depends(leaders)):
    target = await load_scoped(principal, member_id)
    if target["status"] != "pending":
        raise HTTPException(status_code=400, detail="Este cadastro já está ativo")
    await db.users.update_one({"id": member_id}, {"$set": {"status": "active"}})
    return await one({**target, "status": "active"})


@router.delete("/{member_id}", response_model=MessageOut)
async def delete_member(member_id: str, principal: dict = Depends(leaders)):
    target = await load_scoped(principal, member_id)
    if target["id"] == principal["id"]:
        raise HTTPException(status_code=400, detail="Você não pode excluir a si mesmo")
    if principal["role"] == SUB and target["status"] != "pending":
        raise HTTPException(status_code=403, detail="Apenas coordenadores podem excluir membros ativos")
    await db.users.delete_one({"id": member_id})
    await db.sessions.delete_many({"user_id": member_id})
    await db.rsvps.delete_many({"user_id": member_id})
    await db.attendance.delete_many({"user_id": member_id})
    return MessageOut(message="Membro removido")
