"""User-facing activity feed from execution logs (orchestration, approvals, manual triggers)."""

from app.db import get_db
from app.services.orchestration import execution_log_to_out


async def activity_feed(page: int, page_size: int) -> tuple[list[dict], int]:
    db = get_db()
    skip = (page - 1) * page_size
    total = await db.execution_logs.count_documents({})
    cursor = (
        db.execution_logs.find({}).sort("created_at", -1).skip(skip).limit(page_size)
    )
    docs = await cursor.to_list(page_size)
    if not docs:
        return [], total

    mids = list({d["meeting_id"] for d in docs})
    aids = list({d["action_item_id"] for d in docs})

    meetings: dict = {}
    async for m in db.meetings.find({"_id": {"$in": mids}}):
        meetings[m["_id"]] = (m.get("title") or "").strip() or "—"

    items: dict = {}
    async for a in db.action_items.find({"_id": {"$in": aids}}):
        desc = (a.get("description") or "").strip()
        items[a["_id"]] = (desc[:140] + "…") if len(desc) > 140 else desc or "—"

    out: list[dict] = []
    for d in docs:
        row = execution_log_to_out(d)
        row["meeting_title"] = meetings.get(d["meeting_id"], "—")
        row["action_item_preview"] = items.get(d["action_item_id"], "—")
        out.append(row)
    return out, total
