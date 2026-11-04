"""Criterion: Leaders mark real attendance after the event.

PUT /api/events/{id}/attendance by a membro -> 403; on a future event -> 400.
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx

from tests.conftest import login


def create_event(client: httpx.Client, date: str) -> dict:
    r = client.post(
        "/events",
        json={
            "title": f"tscheck-attendance-{uuid.uuid4().hex[:8]}",
            "description": "",
            "date": date,
            "time": "",
            "location": "",
            "sector_id": None,
            "escala_open": True,
            "slots": None,
            "roles": [],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_attendance_rejected_for_member_and_future_event(client: httpx.Client):
    login(client, "admin", "admin123")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    past_ev = create_event(client, yesterday)
    future_ev = create_event(client, tomorrow)

    try:
        # future event -> 400 even for a coordinator
        resp_future = client.put(f"/events/{future_ev['id']}/attendance", json={"present_user_ids": []})
        assert resp_future.status_code == 400, resp_future.text

        # happy path: coordinator marks attendance on a past event
        ok = client.put(f"/events/{past_ev['id']}/attendance", json={"present_user_ids": []})
        assert ok.status_code == 200, ok.text

        # membro is forbidden regardless of event timing
        with httpx.Client(base_url=client.base_url, timeout=30.0) as member_client:
            login(member_client, "joao", "membro123")
            resp_member = member_client.put(f"/events/{past_ev['id']}/attendance", json={"present_user_ids": []})
            assert resp_member.status_code == 403, resp_member.text
    finally:
        client.delete(f"/events/{past_ev['id']}")
        client.delete(f"/events/{future_ev['id']}")
