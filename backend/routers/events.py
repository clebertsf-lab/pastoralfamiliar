import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from lib.auth import COORD, SUB, get_current_user, require_roles
from lib.dates import today_iso
from lib.db import db
from models.event import AttendanceIn, EventIn, EventOut, EventRoleOut, Helper, RsvpIn
from models.user import MessageOut

router = APIRouter(prefix="/events", tags=["events"])
coord_only = require_roles(COORD)
leaders = require_roles(COORD, SUB)
TZ = "America/Sao_Paulo"


def can_respond(user: dict, ev: dict) -> bool:
    return not ev.get("sector_id") or user["role"] == COORD or ev["sector_id"] in (user.get("sector_ids") or [])


def eligible(u: dict, ev: dict) -> bool:
    return not ev.get("sector_id") or ev["sector_id"] in (u.get("sector_ids") or [])


async def build(docs: list[dict], user: dict) -> list[EventOut]:
    if not docs:
        return []
    today = today_iso(TZ)
    ids = [d["id"] for d in docs]
    is_leader = user["role"] in (COORD, SUB)
    rsvps = await db.rsvps.find({"event_id": {"$in": ids}}).sort("created_at", 1).to_list(20000)
    active = await db.users.find(
        {"status": "active"}, {"_id": 0, "id": 1, "name": 1, "phone": 1, "sector_ids": 1}
    ).sort("name", 1).to_list(5000)
    users = {u["id"]: u for u in active}
    sectors = {s["id"]: s["name"] for s in await db.sectors.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)}
    attendance: dict[str, list[str]] = {}
    if is_leader:
        for a in await db.attendance.find({"event_id": {"$in": ids}}).to_list(20000):
            attendance.setdefault(a["event_id"], []).append(a["user_id"])

    def helper(u: dict, role_id: Optional[str] = None, role_names: dict | None = None) -> Helper:
        return Helper(
            user_id=u["id"],
            name=u["name"],
            phone=u.get("phone") if is_leader else None,
            role_id=role_id,
            role_name=(role_names or {}).get(role_id or ""),
        )

    out = []
    for d in docs:
        roles = d.get("roles") or []
        role_names = {r["id"]: r["name"] for r in roles}
        going, declined, responded, mine, my_role = [], [], set(), None, None
        for r in rsvps:
            if r["event_id"] != d["id"] or r["user_id"] not in users:
                continue
            responded.add(r["user_id"])
            u = users[r["user_id"]]
            if r["response"] == "going":
                rid = r.get("role_id") if r.get("role_id") in role_names else None
                going.append(helper(u, rid, role_names))
            else:
                declined.append(helper(u))
            if r["user_id"] == user["id"]:
                mine, my_role = r["response"], r.get("role_id")
        pending = (
            [helper(u) for u in active if u["id"] not in responded and eligible(u, d)]
            if is_leader and d.get("escala_open")
            else []
        )
        out.append(
            EventOut(
                **{k: v for k, v in d.items() if k not in ("_id", "roles")},
                roles=[
                    EventRoleOut(**r, taken=sum(1 for h in going if h.role_id == r["id"])) for r in roles
                ],
                sector_name=sectors.get(d.get("sector_id") or ""),
                helpers=going,
                declined=declined if is_leader else [],
                pending=pending,
                declined_count=len(declined),
                attendance=attendance.get(d["id"], []),
                my_response=mine,
                my_role_id=my_role,
                can_respond=can_respond(user, d),
                can_manage=is_leader,
                can_mark_attendance=is_leader and d["date"] <= today,
                is_past=d["date"] < today,
            )
        )
    return out


async def get_event_doc(event_id: str) -> dict:
    doc = await db.events.find_one({"id": event_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return doc


async def clean_sector(sector_id: str | None) -> str | None:
    if sector_id and not await db.sectors.find_one({"id": sector_id}):
        raise HTTPException(status_code=400, detail="Setor inválido")
    return sector_id or None


def event_fields(body: EventIn) -> dict:
    data = body.model_dump(exclude={"roles"})
    data["roles"] = [
        {"id": r.id or str(uuid.uuid4()), "name": r.name.strip(), "slots": r.slots} for r in body.roles if r.name.strip()
    ]
    return data


@router.get("", response_model=List[EventOut])
async def list_events(
    scope: Literal["upcoming", "past"] = "upcoming",
    month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    user: dict = Depends(get_current_user),
):
    today = today_iso(TZ)
    if month:
        cursor = db.events.find({"date": {"$gte": f"{month}-01", "$lte": f"{month}-31"}}).sort([("date", 1), ("time", 1)])
    elif scope == "upcoming":
        cursor = db.events.find({"date": {"$gte": today}}).sort([("date", 1), ("time", 1)])
    else:
        cursor = db.events.find({"date": {"$lt": today}}).sort([("date", -1), ("time", -1)])
    return await build(await cursor.to_list(500), user)


@router.post("", response_model=EventOut, status_code=201)
async def create_event(body: EventIn, user: dict = Depends(coord_only)):
    doc = {
        **event_fields(body),
        "sector_id": await clean_sector(body.sector_id),
        "id": str(uuid.uuid4()),
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc),
    }
    await db.events.insert_one(doc)
    return (await build([doc], user))[0]


@router.put("/{event_id}", response_model=EventOut)
async def update_event(event_id: str, body: EventIn, user: dict = Depends(coord_only)):
    await get_event_doc(event_id)
    update = {**event_fields(body), "sector_id": await clean_sector(body.sector_id)}
    await db.events.update_one({"id": event_id}, {"$set": update})
    await db.attendance.update_many({"event_id": event_id}, {"$set": {"event_date": body.date}})
    return (await build([await get_event_doc(event_id)], user))[0]


@router.delete("/{event_id}", response_model=MessageOut)
async def delete_event(event_id: str, _: dict = Depends(coord_only)):
    await get_event_doc(event_id)
    await db.events.delete_one({"id": event_id})
    await db.rsvps.delete_many({"event_id": event_id})
    await db.attendance.delete_many({"event_id": event_id})
    return MessageOut(message="Evento removido")


@router.post("/{event_id}/rsvp", response_model=EventOut)
async def rsvp(event_id: str, body: RsvpIn, user: dict = Depends(get_current_user)):
    ev = await get_event_doc(event_id)
    if not ev.get("escala_open"):
        raise HTTPException(status_code=400, detail="A escala deste evento está fechada")
    if ev["date"] < today_iso(TZ):
        raise HTTPException(status_code=400, detail="Este evento já aconteceu")
    if not can_respond(user, ev):
        raise HTTPException(status_code=403, detail="Esta escala é exclusiva para o setor do evento")
    role_id = None
    roles = {r["id"]: r for r in ev.get("roles") or []}
    if body.response == "going":
        others = {"event_id": event_id, "response": "going", "user_id": {"$ne": user["id"]}}
        if roles:
            if body.role_id not in roles:
                raise HTTPException(status_code=400, detail="Escolha uma função para ajudar")
            role_id = body.role_id
            slots = roles[role_id].get("slots")
            if slots and await db.rsvps.count_documents({**others, "role_id": role_id}) >= slots:
                raise HTTPException(status_code=409, detail="As vagas desta função já foram preenchidas")
        elif ev.get("slots") and await db.rsvps.count_documents(others) >= ev["slots"]:
            raise HTTPException(status_code=409, detail="As vagas desta escala já foram preenchidas")
    await db.rsvps.update_one(
        {"event_id": event_id, "user_id": user["id"]},
        {
            "$set": {"response": body.response, "role_id": role_id, "created_at": datetime.now(timezone.utc)},
            "$setOnInsert": {"id": str(uuid.uuid4())},
        },
        upsert=True,
    )
    return (await build([ev], user))[0]


@router.delete("/{event_id}/rsvp", response_model=EventOut)
async def clear_rsvp(event_id: str, user: dict = Depends(get_current_user)):
    ev = await get_event_doc(event_id)
    await db.rsvps.delete_one({"event_id": event_id, "user_id": user["id"]})
    return (await build([ev], user))[0]


@router.put("/{event_id}/attendance", response_model=EventOut)
async def set_attendance(event_id: str, body: AttendanceIn, user: dict = Depends(leaders)):
    ev = await get_event_doc(event_id)
    if ev["date"] > today_iso(TZ):
        raise HTTPException(status_code=400, detail="A presença só pode ser marcada no dia do evento ou depois")
    wanted = list(dict.fromkeys(body.present_user_ids))
    valid = [u["id"] for u in await db.users.find({"id": {"$in": wanted}, "status": "active"}, {"id": 1}).to_list(2000)]
    await db.attendance.delete_many({"event_id": event_id})
    now = datetime.now(timezone.utc)
    if valid:
        await db.attendance.insert_many(
            [
                {"id": str(uuid.uuid4()), "event_id": event_id, "user_id": uid, "event_date": ev["date"],
                 "marked_by": user["id"], "marked_at": now}
                for uid in valid
            ]
        )
    return (await build([ev], user))[0]
