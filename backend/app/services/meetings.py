from bson import ObjectId
from bson.errors import InvalidId

from app.db import get_db
from app.schemas.common import oid_str


async def get_meeting_or_none(meeting_id: str) -> dict | None:
    try:
        oid = ObjectId(meeting_id)
    except InvalidId:
        return None
    return await get_db().meetings.find_one({"_id": oid})


async def load_meeting_detail(meeting_id: str) -> dict | None:
    db = get_db()
    meeting = await get_meeting_or_none(meeting_id)
    if not meeting:
        return None
    mid = meeting["_id"]
    transcript = await db.transcripts.find_one({"meeting_id": mid})
    links = await db.meeting_participants.find({"meeting_id": mid}).to_list(None)
    participant_ids = [l["participant_id"] for l in links]
    participants_by_id: dict = {}
    if participant_ids:
        async for p in db.participants.find({"_id": {"$in": participant_ids}}):
            participants_by_id[p["_id"]] = p
    participants_out = []
    for link in links:
        pid = link["participant_id"]
        p = participants_by_id.get(pid)
        if not p:
            continue
        participants_out.append(
            {
                "participant": {
                    "id": oid_str(p["_id"]),
                    "display_name": p["display_name"],
                    "email": p.get("email"),
                },
                "role": link.get("role"),
            }
        )
    action_items = await db.action_items.find({"meeting_id": mid}).sort("created_at", 1).to_list(None)
    logs = await db.processing_logs.find({"meeting_id": mid}).sort("timestamp", 1).to_list(None)

    return {
        "meeting": meeting,
        "transcript": transcript,
        "participants": participants_out,
        "action_items": action_items,
        "processing_logs": logs,
    }


async def load_meeting_participants_and_logs_by_oid(meeting_oid: ObjectId) -> dict:
    """Sidebar-style data for meeting detail / review item (no transcript or action items)."""
    db = get_db()
    links = await db.meeting_participants.find({"meeting_id": meeting_oid}).to_list(None)
    participant_ids = [l["participant_id"] for l in links]
    participants_by_id: dict = {}
    if participant_ids:
        async for p in db.participants.find({"_id": {"$in": participant_ids}}):
            participants_by_id[p["_id"]] = p
    participants_out = []
    for link in links:
        pid = link["participant_id"]
        p = participants_by_id.get(pid)
        if not p:
            continue
        participants_out.append(
            {
                "participant": {
                    "id": oid_str(p["_id"]),
                    "display_name": p["display_name"],
                    "email": p.get("email"),
                },
                "role": link.get("role"),
            }
        )
    logs = await db.processing_logs.find({"meeting_id": meeting_oid}).sort("timestamp", 1).to_list(None)
    return {"participants": participants_out, "processing_logs": logs}
