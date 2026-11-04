"""Criterion: Functions with slots in escala.

POST rsvp going without role_id -> 400 when the event has roles; a full function -> 409.
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx

from tests.conftest import login


def test_rsvp_requires_role_and_respects_slot_limit(client: httpx.Client):
    login(client, "admin", "admin123")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    create = client.post(
        "/events",
        json={
            "title": f"tscheck-roles-{uuid.uuid4().hex[:8]}",
            "description": "",
            "date": tomorrow,
            "time": "",
            "location": "",
            "sector_id": None,
            "escala_open": True,
            "slots": None,
            "roles": [{"id": None, "name": "Leitura", "slots": 1}],
        },
    )
    assert create.status_code == 201, create.text
    event = create.json()
    role_id = event["roles"][0]["id"]

    try:
        with httpx.Client(base_url=client.base_url, timeout=30.0) as joao_client, httpx.Client(
            base_url=client.base_url, timeout=30.0
        ) as ana_client:
            login(joao_client, "joao", "membro123")
            login(ana_client, "ana", "membro123")

            # going without role_id -> 400
            bad = joao_client.post(f"/events/{event['id']}/rsvp", json={"response": "going"})
            assert bad.status_code == 400, bad.text

            # first volunteer takes the single slot
            ok = joao_client.post(f"/events/{event['id']}/rsvp", json={"response": "going", "role_id": role_id})
            assert ok.status_code == 200, ok.text
            assert ok.json()["roles"][0]["taken"] == 1

            # second volunteer hits the full slot -> 409
            full = ana_client.post(f"/events/{event['id']}/rsvp", json={"response": "going", "role_id": role_id})
            assert full.status_code == 409, full.text

            # undo joao's rsvp
            undo = joao_client.delete(f"/events/{event['id']}/rsvp")
            assert undo.status_code == 200, undo.text
    finally:
        client.delete(f"/events/{event['id']}")
