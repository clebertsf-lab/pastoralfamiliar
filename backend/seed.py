"""Idempotent sample data: run `cd /app/backend && python seed.py`. Skips if sample sectors exist."""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

from lib.auth import COORD, MEMBER, SUB, ensure_default_admin, hash_password
from lib.dates import today_iso
from lib.db import db, ensure_indexes


def uid() -> str:
    return str(uuid.uuid4())


async def seed_past_event() -> None:
    """Adds one past event with confirmed attendance (idempotent by title)."""
    if await db.events.find_one({"title": "Missa de Abertura do Ano Pastoral"}):
        return
    today = date.fromisoformat(today_iso("America/Sao_Paulo"))
    ev_date = (today - timedelta(days=7)).isoformat()
    now = datetime.now(timezone.utc)
    ev = {"id": uid(), "title": "Missa de Abertura do Ano Pastoral", "description": "Celebração de envio.",
          "date": ev_date, "time": "19:00", "location": "Igreja Matriz", "sector_id": None, "escala_open": True,
          "slots": None, "roles": [], "created_at": now, "created_by": None}
    await db.events.insert_one(ev)
    people = await db.users.find({"username": {"$in": ["joao", "ana", "sub"]}}).to_list(10)
    for u in people:
        await db.rsvps.insert_one({"id": uid(), "event_id": ev["id"], "user_id": u["id"], "response": "going",
                                   "role_id": None, "created_at": now})
    for u in people[:2]:
        await db.attendance.insert_one({"id": uid(), "event_id": ev["id"], "user_id": u["id"], "event_date": ev_date,
                                        "marked_by": None, "marked_at": now})


async def main() -> None:
    await ensure_indexes()
    await ensure_default_admin()
    if await db.sectors.count_documents({}) > 0:
        await seed_past_event()
        print("Seed já aplicado — evento passado garantido.")
        return
    now = datetime.now(timezone.utc)
    sectors = [
        {"id": uid(), "name": "Liturgia & Canto", "description": "Leituras, salmos e música nas celebrações"},
        {"id": uid(), "name": "Acolhida", "description": "Recepção dos fiéis na porta da igreja"},
        {"id": uid(), "name": "Ação Social", "description": "Visitas, cestas básicas e caridade"},
    ]
    await db.sectors.insert_many(sectors)
    liturgia, acolhida, social = (s["id"] for s in sectors)

    people = [
        ("sub", "sub123", "Maria Aparecida Souza", "(11) 98765-4321", SUB, [liturgia], "Toca violão, disponível aos sábados"),
        ("joao", "membro123", "João Batista Lima", "(11) 91234-5678", MEMBER, [liturgia, acolhida], "Leitor experiente"),
        ("ana", "membro123", "Ana Clara Ferreira", "(11) 99876-1234", MEMBER, [acolhida], ""),
        ("pedro", "membro123", "Pedro Henrique Alves", "(11) 97654-3210", MEMBER, [social], "Tem carro para entregas"),
        ("lucia", "membro123", "Lúcia Mendes", "(11) 96543-2109", MEMBER, [acolhida], "Prefere missas da manhã"),
    ]
    users = []
    for username, pw, name, phone, role, sector, notes in people:
        users.append({
            "id": uid(), "username": username, "password_hash": hash_password(pw), "name": name,
            "phone": phone, "notes": notes, "role": role, "sector_ids": sector, "status": "active", "created_at": now,
        })
    users.append({
        "id": uid(), "username": "teresa", "password_hash": hash_password("membro123"), "name": "Teresa Rocha",
        "phone": "(11) 95555-0000", "notes": "Pediu para entrar na Acolhida", "role": MEMBER,
        "sector_ids": [acolhida], "status": "pending", "created_at": now,
    })
    await db.users.insert_many(users)

    today = date.fromisoformat(today_iso("America/Sao_Paulo"))
    d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
    events = [
        {"title": "Missa da Comunidade", "description": "Precisamos de leitores, ministros e acolhida.", "date": d(3),
         "time": "19:00", "location": "Igreja Matriz", "sector_id": None, "escala_open": True, "slots": None,
         "roles": [{"id": uid(), "name": "Leitura", "slots": 2}, {"id": uid(), "name": "Acolhida", "slots": 3},
                   {"id": uid(), "name": "Canto", "slots": 2}]},
        {"title": "Ensaio do Coral", "description": "Preparação dos cantos do mês.", "date": d(5),
         "time": "20:00", "location": "Salão Paroquial", "sector_id": liturgia, "escala_open": True, "slots": None},
        {"title": "Entrega de Cestas Básicas", "description": "Montagem e entrega às famílias assistidas.",
         "date": d(10), "time": "08:30", "location": "Centro Pastoral", "sector_id": social, "escala_open": True, "slots": 6},
        {"title": "Reunião Geral da Pastoral", "description": "Planejamento do próximo semestre.", "date": d(14),
         "time": "19:30", "location": "Salão Paroquial", "sector_id": None, "escala_open": False, "slots": None},
    ]
    for e in events:
        e.update({"id": uid(), "created_at": now, "created_by": None})
    await db.events.insert_many(events)

    by_name = {u["username"]: u["id"] for u in users}
    rsvps = [
        (events[0]["id"], by_name["joao"], "going"),
        (events[0]["id"], by_name["ana"], "going"),
        (events[0]["id"], by_name["pedro"], "not_going"),
        (events[1]["id"], by_name["sub"], "going"),
        (events[2]["id"], by_name["pedro"], "going"),
    ]
    await db.rsvps.insert_many(
        [{"id": uid(), "event_id": e, "user_id": u, "response": r, "created_at": now} for e, u, r in rsvps]
    )
    await seed_past_event()
    print("Seed aplicado.")


if __name__ == "__main__":
    asyncio.run(main())
