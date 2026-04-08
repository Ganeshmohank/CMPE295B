"""Meeting attendees + project roster; add people to a meeting (and optionally the linked project)."""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.db import get_db
from app.schemas.common import oid_str
from app.schemas.participant import MeetingParticipantOut, ParticipantOut
from app.services.meetings import get_meeting_or_none


def _participant_to_row(p: dict, role: str | None) -> dict:
    return {
        "participant": {
            "id": oid_str(p["_id"]),
            "display_name": p["display_name"],
            "email": p.get("email"),
        },
        "role": role,
    }


async def list_project_team_member_rows(project_id: ObjectId) -> list[dict]:
    db = get_db()
    doc = await db.projects.find_one({"_id": project_id})
    if not doc:
        return []
    raw_ids = doc.get("team_member_ids") or []
    if not raw_ids:
        return []
    oids = [x for x in raw_ids if isinstance(x, ObjectId)]
    if not oids:
        return []
    by_id: dict = {}
    async for p in db.participants.find({"_id": {"$in": oids}}):
        by_id[p["_id"]] = p
    out: list[dict] = []
    for oid in oids:
        p = by_id.get(oid)
        if p:
            out.append(_participant_to_row(p, "project"))
    return out


async def add_meeting_team_member(
    meeting_id: str,
    display_name: str,
    email: str | None,
    add_to_linked_project: bool,
) -> MeetingParticipantOut:
    db = get_db()
    meeting = await get_meeting_or_none(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    mid = meeting["_id"]
    name = display_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="display_name is required")

    email_norm = email.strip().lower() if email and email.strip() else None
    pid: ObjectId | None = None
    if email_norm:
        existing = await db.participants.find_one({"email": email_norm})
        if existing:
            pid = existing["_id"]

    if pid is None:
        doc: dict = {"display_name": name, "created_at": datetime.now(timezone.utc)}
        if email_norm:
            doc["email"] = email_norm
        try:
            ins = await db.participants.insert_one(doc)
            pid = ins.inserted_id
        except DuplicateKeyError:
            if not email_norm:
                raise HTTPException(status_code=409, detail="Could not create participant") from None
            ex = await db.participants.find_one({"email": email_norm})
            if not ex:
                raise HTTPException(status_code=409, detail="Could not create participant") from None
            pid = ex["_id"]

    assert pid is not None
    now = datetime.now(timezone.utc)
    await db.meeting_participants.update_one(
        {"meeting_id": mid, "participant_id": pid},
        {"$setOnInsert": {"role": "team", "joined_at": now}},
        upsert=True,
    )

    n = await db.meeting_participants.count_documents({"meeting_id": mid})
    await db.meetings.update_one(
        {"_id": mid},
        {"$set": {"participants_count": n, "updated_at": now}},
    )

    proj_id = meeting.get("project_id")
    if add_to_linked_project and isinstance(proj_id, ObjectId):
        await db.projects.update_one(
            {"_id": proj_id},
            {"$addToSet": {"team_member_ids": pid}, "$set": {"updated_at": now}},
        )

    p = await db.participants.find_one({"_id": pid})
    if not p:
        raise HTTPException(status_code=500, detail="Participant missing after insert")
    link = await db.meeting_participants.find_one({"meeting_id": mid, "participant_id": pid})
    role = link.get("role") if link else "team"
    row = _participant_to_row(p, role)
    return MeetingParticipantOut(**row)
