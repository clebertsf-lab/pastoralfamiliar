"""Member participation stats (confirmed attendance) and safe user serialization."""

from datetime import datetime, timezone

from lib.db import db
from models.user import UserPublic


def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def served_stats(user_ids: list[str]) -> dict[str, tuple[int, str | None]]:
    if not user_ids:
        return {}
    rows = await db.attendance.aggregate(
        [
            {"$match": {"user_id": {"$in": user_ids}}},
            {"$group": {"_id": "$user_id", "count": {"$sum": 1}, "last": {"$max": "$event_date"}}},
        ]
    ).to_list(None)
    return {r["_id"]: (r["count"], r["last"]) for r in rows}


def to_public(doc: dict, stats: dict[str, tuple[int, str | None]] | None = None, hide_notes: bool = False) -> UserPublic:
    count, last = (stats or {}).get(doc["id"], (0, None))
    return UserPublic(
        **{
            **doc,
            "sector_ids": doc.get("sector_ids") or [],
            "notes": None if hide_notes else doc.get("notes", ""),
            "last_seen_at": aware(doc.get("last_seen_at")),
            "created_at": aware(doc.get("created_at")),
            "served_count": count,
            "last_served": last,
        }
    )
