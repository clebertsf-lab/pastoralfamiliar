"""Criterion: Monthly calendar view — GET /api/events?month=YYYY-MM returns events for that month
regardless of upcoming/past scope."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx

from tests.conftest import login


def test_month_query_returns_events_in_that_month_only(client: httpx.Client):
    login(client, "admin", "admin123")
    far_future = datetime.now(timezone.utc) + timedelta(days=200)
    date_str = far_future.strftime("%Y-%m-%d")
    ym = far_future.strftime("%Y-%m")
    other_ym = (far_future + timedelta(days=60)).strftime("%Y-%m")

    create = client.post(
        "/events",
        json={
            "title": f"tscheck-calendar-{uuid.uuid4().hex[:8]}",
            "description": "",
            "date": date_str,
            "time": "",
            "location": "",
            "sector_id": None,
            "escala_open": True,
            "slots": None,
            "roles": [],
        },
    )
    assert create.status_code == 201, create.text
    event_id = create.json()["id"]

    try:
        in_month = client.get("/events", params={"month": ym})
        assert in_month.status_code == 200, in_month.text
        assert any(e["id"] == event_id for e in in_month.json())
        for e in in_month.json():
            assert e["date"].startswith(ym)

        other_month = client.get("/events", params={"month": other_ym})
        assert other_month.status_code == 200
        assert not any(e["id"] == event_id for e in other_month.json())
    finally:
        client.delete(f"/events/{event_id}")
