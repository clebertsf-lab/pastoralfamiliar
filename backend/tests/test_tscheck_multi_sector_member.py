"""Criterion: Member can belong to multiple sectors."""

import uuid

import httpx

from tests.conftest import login


def test_member_can_have_multiple_sectors(client: httpx.Client):
    login(client, "admin", "admin123")

    sectors = client.get("/sectors/options")
    assert sectors.status_code == 200
    sector_ids = [s["id"] for s in sectors.json()]
    assert len(sector_ids) >= 2, "need at least 2 sectors seeded to exercise this criterion"
    two = sector_ids[:2]

    uname = f"tscheck-multisector-{uuid.uuid4().hex[:8]}"
    create = client.post(
        "/members",
        json={
            "username": uname,
            "password": "senha123",
            "name": "TSCheck MultiSector",
            "phone": "",
            "notes": "",
            "role": "membro",
            "sector_ids": [two[0]],
        },
    )
    assert create.status_code == 201, create.text
    member_id = create.json()["id"]
    assert create.json()["sector_ids"] == [two[0]]

    try:
        update = client.put(
            f"/members/{member_id}",
            json={
                "name": "TSCheck MultiSector",
                "phone": "",
                "notes": "",
                "role": "membro",
                "sector_ids": two,
            },
        )
        assert update.status_code == 200, update.text
        body = update.json()
        assert sorted(body["sector_ids"]) == sorted(two), body

        listed = client.get("/members?status=active")
        assert listed.status_code == 200
        row = next(m for m in listed.json() if m["id"] == member_id)
        assert sorted(row["sector_ids"]) == sorted(two)
    finally:
        client.delete(f"/members/{member_id}")
