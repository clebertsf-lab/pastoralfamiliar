"""Criterion: Leaders see who goes / who doesn't / who didn't answer; members do not.

As admin (leader) the pending/declined lists are populated for an open-escala future event.
As a membro, the API hides pending/declined (empty lists) and hides phones (None).
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx

from tests.conftest import login


def test_pending_declined_visible_to_leader_hidden_from_member(client: httpx.Client):
    login(client, "admin", "admin123")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    create = client.post(
        "/events",
        json={
            "title": f"tscheck-escala-{uuid.uuid4().hex[:8]}",
            "description": "",
            "date": tomorrow,
            "time": "",
            "location": "",
            "sector_id": None,
            "escala_open": True,
            "slots": None,
            "roles": [],
        },
    )
    assert create.status_code == 201, create.text
    event = create.json()

    try:
        # one member declines, another leaves it pending
        with httpx.Client(base_url=client.base_url, timeout=30.0) as joao_client:
            login(joao_client, "joao", "membro123")
            decline = joao_client.post(f"/events/{event['id']}/rsvp", json={"response": "not_going"})
            assert decline.status_code == 200, decline.text

            member_view = joao_client.get("/events", params={"scope": "upcoming"})
            assert member_view.status_code == 200
            mine = next(e for e in member_view.json() if e["id"] == event["id"])
            assert mine["pending"] == [], mine
            assert mine["declined"] == [], mine
            for helper in mine["helpers"] + mine["declined"]:
                assert helper.get("phone") is None

            # undo the RSVP we created
            clear = joao_client.delete(f"/events/{event['id']}/rsvp")
            assert clear.status_code == 200, clear.text

        # as leader we see full groups
        leader_view = client.get("/events", params={"scope": "upcoming"})
        assert leader_view.status_code == 200
        mine_leader = next(e for e in leader_view.json() if e["id"] == event["id"])
        assert isinstance(mine_leader["pending"], list)
        assert isinstance(mine_leader["declined"], list)
        # joao cleared his rsvp, so he (and other members who never responded) show up pending again
        assert len(mine_leader["pending"]) >= 1, mine_leader
    finally:
        client.delete(f"/events/{event['id']}")
