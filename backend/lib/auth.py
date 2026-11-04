"""Auth + authorization helpers. Sessions are opaque tokens in an httpOnly cookie; the
principal (role, sector, status) is re-read from Mongo on every request, never trusted
from the client."""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response

from lib.db import db

COOKIE_NAME = "pastoral_session"
SESSION_DAYS = 30
COORD = "coordenador"
SUB = "subcoordenador"
MEMBER = "membro"
ROLES = (COORD, SUB, MEMBER)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${dk}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, dk = stored.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return hmac.compare_digest(check, dk)


async def start_session(response: Response, user_id: str) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    await db.sessions.insert_one({"token": token, "user_id": user_id, "expires_at": expires})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


async def end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await db.sessions.delete_one({"token": token})
    response.delete_cookie(COOKIE_NAME, path="/")


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")
    session = await db.sessions.find_one(
        {"token": token, "expires_at": {"$gt": datetime.now(timezone.utc)}}
    )
    if not session:
        raise HTTPException(status_code=401, detail="Sessão expirada")
    user = await db.users.find_one({"id": session["user_id"], "status": "active"})
    if not user:
        raise HTTPException(status_code=401, detail="Usuário inativo")
    await touch_last_seen(user)
    return user


async def touch_last_seen(user: dict) -> None:
    """Record app access; throttled to one write every 2 minutes per user."""
    now = datetime.now(timezone.utc)
    last = user.get("last_seen_at")
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is None or now - last > timedelta(minutes=2):
        await db.users.update_one({"id": user["id"]}, {"$set": {"last_seen_at": now}})
        user["last_seen_at"] = now


async def migrate_users() -> None:
    """One-way migration: single `sector_id` → list `sector_ids`."""
    await db.users.update_many(
        {"sector_id": {"$exists": True}},
        [
            {"$set": {"sector_ids": {"$cond": [{"$ifNull": ["$sector_id", False]}, ["$sector_id"], []]}}},
            {"$unset": "sector_id"},
        ],
    )
    await db.users.update_many({"sector_ids": {"$exists": False}}, {"$set": {"sector_ids": []}})


def require_roles(*roles: str):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Permissão negada")
        return user

    return dep


def member_scope(principal: dict) -> dict:
    """Mongo predicate of the members a principal may manage (fail-closed)."""
    if principal["role"] == COORD:
        return {}
    if principal["role"] == SUB and principal.get("sector_ids"):
        return {"sector_ids": {"$in": principal["sector_ids"]}}
    return {"id": "__none__"}


async def ensure_default_admin() -> None:
    """Guarantee at least one coordinator exists so the app is never locked out."""
    if await db.users.find_one({"role": COORD}):
        return
    await db.users.update_one(
        {"username": "admin"},
        {
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "username": "admin",
                "password_hash": hash_password("admin123"),
                "name": "Coordenador Geral",
                "phone": "",
                "notes": "",
                "role": COORD,
                "sector_ids": [],
                "status": "active",
                "created_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
