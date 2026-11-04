import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from lib.auth import (
    MEMBER,
    end_session,
    get_current_user,
    hash_password,
    start_session,
    touch_last_seen,
    verify_password,
)
from lib.db import db
from lib.stats import served_stats, to_public
from models.user import LoginIn, MessageOut, SignupIn, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


async def to_self(user: dict) -> UserPublic:
    # Own profile never carries the coordinators' private notes.
    return to_public(user, await served_stats([user["id"]]), hide_notes=True)


@router.post("/login", response_model=UserPublic)
async def login(body: LoginIn, response: Response):
    user = await db.users.find_one({"username": body.username.strip().lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="Seu cadastro ainda aguarda aprovação da coordenação")
    await start_session(response, user["id"])
    user["last_seen_at"] = None
    await touch_last_seen(user)
    return await to_self(user)


@router.post("/logout", response_model=MessageOut)
async def logout(request: Request, response: Response):
    await end_session(request, response)
    return MessageOut(message="ok")


@router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return await to_self(user)


@router.post("/signup", response_model=MessageOut, status_code=201)
async def signup(body: SignupIn):
    username = body.username.strip().lower()
    if await db.users.find_one({"username": username}):
        raise HTTPException(status_code=409, detail="Este usuário já está em uso")
    wanted = list(dict.fromkeys(body.sector_ids))
    existing = {s["id"] for s in await db.sectors.find({"id": {"$in": wanted}}, {"id": 1}).to_list(100)}
    await db.users.insert_one(
        {
            "id": str(uuid.uuid4()),
            "username": username,
            "password_hash": hash_password(body.password),
            "name": body.name.strip(),
            "phone": body.phone.strip(),
            "notes": body.notes.strip(),
            "role": MEMBER,
            "sector_ids": [s for s in wanted if s in existing],
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        }
    )
    return MessageOut(message="Cadastro enviado! Aguarde a aprovação da coordenação.")
