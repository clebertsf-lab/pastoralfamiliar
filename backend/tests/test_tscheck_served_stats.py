"""Criterion: Last time each member served + participation count (confirmed attendance only)."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx

from tests.conftest import login


def test_served_count_and_last_served_from_confirmed_attendance(client: httpx.Client):
    login(client, "admin", "admin123")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    uname = f"tscheck-served-{uuid.uuid4().hex[:8]}"
    member = client.post(
        "/members",
        json={
            "username": uname,
            "password": "senha123",
            "name": "TSCheck Served",
            "phone": "",
            "notes": "",
            "role": "membro",
            "sector_ids": [],
        },
    )
    assert member.status_code == 201, member.text
    member_id = member.json()["id"]
    assert member.json()["served_count"] == 0
    assert member.json()["last_served"] is None

    event = client.post(
        "/events",
        json={
            "title": f"tscheck-servedevt-{uuid.uuid4().hex[:8]}",
            "description": "",
            "date": yesterday,
            "time": "",
            "location": "",
            "sector_id": None,
            "escala_open": True,
            "slots": None,
            "roles": [],
        },
    )
    assert event.status_code == 201, event.text
    event_id = event.json()["id"]

    try:
        mark = client.put(f"/events/{event_id}/attendance", json={"present_user_ids": [member_id]})
        assert mark.status_code == 200, mark.text

        listed = client.get("/members?status=active")
        row = next(m for m in listed.json() if m["id"] == member_id)
        assert row["served_count"] == 1, row
        assert row["last_served"] == yesterday, row

        history = client.get(f"/members/{member_id}/history")
        assert history.status_code == 200, history.text
        assert any(h["event_id"] == event_id for h in history.json())

        # RSVPing alone (no attendance) must NOT bump served_count for a different event
        rsvp_only_event = client.post(
            "/events",
            json={
                "title": f"tscheck-rsvponly-{uuid.uuid4().hex[:8]}",
                "description": "",
                "date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d"),
                "time": "",
                "location": "",
                "sector_id": None,
                "escala_open": True,
                "slots": None,
                "roles": [],
            },
        )
        assert rsvp_only_event.status_code == 201
        rsvp_event_id = rsvp_only_event.json()["id"]
        try:
            with httpx.Client(base_url=client.base_url, timeout=30.0) as member_client:
                login(member_client, uname, "senha123")
                r = member_client.post(f"/events/{rsvp_event_id}/rsvp", json={"response": "going"})
                assert r.status_code == 200, r.text
            still = client.get("/members?status=active")
            row2 = next(m for m in still.json() if m["id"] == member_id)
            assert row2["served_count"] == 1, "RSVP alone must not count as served"
        finally:
            client.delete(f"/events/{rsvp_event_id}")
    finally:
        client.delete(f"/events/{event_id}")
        client.delete(f"/members/{member_id}")
