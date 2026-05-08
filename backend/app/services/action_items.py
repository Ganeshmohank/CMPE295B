from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from app.db import get_db
from app.domain.enums import ActionItemStatus
from app.schemas.action_item import ActionItemUpdate
from app.services import meetings as meetings_service
from app.services import orchestration as orchestration_service


def _parse_id(item_id: str) -> ObjectId:
    try:
        oid = ObjectId(item_id)
    except InvalidId as e:
        raise HTTPException(status_code=404, detail="Action item not found") from e
    return oid


ALLOWED_TRANSITIONS: dict[ActionItemStatus, set[ActionItemStatus]] = {
    ActionItemStatus.PENDING_REVIEW: {
        ActionItemStatus.APPROVED,
        ActionItemStatus.REJECTED,
        ActionItemStatus.PENDING_REVIEW,
    },
    ActionItemStatus.APPROVED: {
        ActionItemStatus.TICKET_CREATED,
        ActionItemStatus.APPROVED,
        ActionItemStatus.PENDING_REVIEW,
    },
    ActionItemStatus.REJECTED: {ActionItemStatus.REJECTED, ActionItemStatus.PENDING_REVIEW},
    ActionItemStatus.TICKET_CREATED: {ActionItemStatus.TICKET_CREATED},
}


def _validate_status_transition(current: str, new: str) -> None:
    try:
        cur = ActionItemStatus(current)
        nxt = ActionItemStatus(new)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid status value") from e
    allowed = ALLOWED_TRANSITIONS.get(cur, set())
    if nxt not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current} to {new}",
        )


async def get_action_item_or_404(item_id: str) -> dict:
    oid = _parse_id(item_id)
    doc = await get_db().action_items.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Action item not found")
    return doc


async def update_action_item(item_id: str, body: ActionItemUpdate) -> dict:
    doc = await get_action_item_or_404(item_id)
    updates: dict = {}
    if body.description is not None:
        updates["description"] = body.description
    if body.owner_name is not None:
        updates["owner_name"] = body.owner_name
    if body.due_date is not None:
        updates["due_date"] = body.due_date.isoformat()
    if body.priority is not None:
        updates["priority"] = body.priority.value
    if body.confidence is not None:
        updates["confidence"] = body.confidence
    if body.source_snippet is not None:
        updates["source_snippet"] = body.source_snippet
    if body.status is not None:
        _validate_status_transition(doc["status"], body.status.value)
        updates["status"] = body.status.value
    if not updates:
        return doc
    updates["updated_at"] = datetime.now(timezone.utc)
    oid = _parse_id(item_id)
    await get_db().action_items.update_one({"_id": oid}, {"$set": updates})
    fresh = await get_db().action_items.find_one({"_id": oid})
    assert fresh is not None
    return fresh


async def approve_action_item(item_id: str, auto_orchestrate: bool = True) -> dict:
    doc = await get_action_item_or_404(item_id)
    if doc["status"] != ActionItemStatus.PENDING_REVIEW.value:
        raise HTTPException(status_code=400, detail="Only pending_review items can be approved")
    oid = _parse_id(item_id)
    await get_db().action_items.update_one(
        {"_id": oid},
        {
            "$set": {
                "status": ActionItemStatus.APPROVED.value,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    fresh = await get_db().action_items.find_one({"_id": oid})
    assert fresh is not None

    if auto_orchestrate:
        db = get_db()
        meeting = await db.meetings.find_one({"_id": doc["meeting_id"]})
        if meeting:
            tctx, other, owner_name, due_s = await orchestration_service.build_classification_context(
                doc["meeting_id"],
                oid,
                doc,
            )
            import asyncio

            asyncio.create_task(
                orchestration_service.execute_auto_orchestration(
                    action_item_id=item_id,
                    meeting_id=str(doc["meeting_id"]),
                    description=doc["description"],
                    priority=doc["priority"],
                    project_theme=meeting.get("project_theme"),
                    meeting_title=meeting["title"],
                    source_snippet=doc.get("source_snippet"),
                    transcript_context=tctx,
                    other_action_items=other,
                    owner_name=owner_name,
                    due_date=due_s,
                    triggered_by="approval",
                )
            )

    return fresh


async def reject_action_item(item_id: str) -> dict:
    doc = await get_action_item_or_404(item_id)
    if doc["status"] != ActionItemStatus.PENDING_REVIEW.value:
        raise HTTPException(status_code=400, detail="Only pending_review items can be rejected")
    oid = _parse_id(item_id)
    await get_db().action_items.update_one(
        {"_id": oid},
        {
            "$set": {
                "status": ActionItemStatus.REJECTED.value,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    fresh = await get_db().action_items.find_one({"_id": oid})
    assert fresh is not None
    return fresh


async def bulk_approve_for_meeting(meeting_id: str) -> int:
    try:
        mid = ObjectId(meeting_id)
    except InvalidId as e:
        raise HTTPException(status_code=404, detail="Meeting not found") from e
    meeting = await get_db().meetings.find_one({"_id": mid})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    result = await get_db().action_items.update_many(
        {"meeting_id": mid, "status": ActionItemStatus.PENDING_REVIEW.value},
        {
            "$set": {
                "status": ActionItemStatus.APPROVED.value,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return int(result.modified_count)


async def bulk_reject_for_meeting(meeting_id: str) -> int:
    try:
        mid = ObjectId(meeting_id)
    except InvalidId as e:
        raise HTTPException(status_code=404, detail="Meeting not found") from e
    meeting = await get_db().meetings.find_one({"_id": mid})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    result = await get_db().action_items.update_many(
        {"meeting_id": mid, "status": ActionItemStatus.PENDING_REVIEW.value},
        {
            "$set": {
                "status": ActionItemStatus.REJECTED.value,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return int(result.modified_count)


async def get_pending_review_one(item_id: str) -> dict:
    doc = await get_action_item_or_404(item_id)
    if doc["status"] != ActionItemStatus.PENDING_REVIEW.value:
        raise HTTPException(
            status_code=400,
            detail="Only pending_review items can be opened here",
        )
    meeting = await get_db().meetings.find_one({"_id": doc["meeting_id"]})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {
        **doc,
        "meeting_title": meeting["title"],
        "meeting_start_time": meeting["start_time"],
    }


async def get_pending_review_detail(item_id: str) -> dict:
    row = await get_pending_review_one(item_id)
    extra = await meetings_service.load_meeting_participants_and_logs_by_oid(row["meeting_id"])
    row["participants"] = extra["participants"]
    row["processing_logs"] = extra["processing_logs"]
    return row


async def get_action_item_detail(item_id: str) -> dict:
    """Get action item detail regardless of status - for orchestrator page."""
    doc = await get_action_item_or_404(item_id)
    meeting = await get_db().meetings.find_one({"_id": doc["meeting_id"]})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {
        **doc,
        "meeting_title": meeting["title"],
        "meeting_start_time": meeting["start_time"],
        "project_theme": meeting.get("project_theme"),
    }


async def list_pending_review_with_meeting_meta() -> list[dict]:
    db = get_db()
    pipeline = [
        {"$match": {"status": ActionItemStatus.PENDING_REVIEW.value}},
        {
            "$lookup": {
                "from": "meetings",
                "localField": "meeting_id",
                "foreignField": "_id",
                "as": "m",
            }
        },
        {"$unwind": "$m"},
        {"$sort": {"confidence": 1, "created_at": 1}},
    ]
    cursor = db.action_items.aggregate(pipeline)
    rows = await cursor.to_list(None)
    out = []
    for row in rows:
        m = row["m"]
        out.append(
            {
                **{k: v for k, v in row.items() if k not in ("m",)},
                "meeting_title": m["title"],
                "meeting_start_time": m["start_time"],
            }
        )
    return out


async def list_pending_review_paginated(
    page: int,
    page_size: int,
) -> tuple[list[dict], int, int]:
    """Pending items for up to ``page_size`` meetings (newest meetings first), sorted like the full queue."""
    db = get_db()
    page = max(1, page)
    page_size = min(10, max(1, page_size))
    skip = (page - 1) * page_size
    st = ActionItemStatus.PENDING_REVIEW.value

    total_pending_items = await db.action_items.count_documents({"status": st})

    pipe_cnt = [
        {"$match": {"status": st}},
        {"$group": {"_id": "$meeting_id"}},
        {"$count": "n"},
    ]
    cdocs = await db.action_items.aggregate(pipe_cnt).to_list(1)
    total_meetings = int(cdocs[0]["n"]) if cdocs else 0

    pipe_mids = [
        {"$match": {"status": st}},
        {
            "$lookup": {
                "from": "meetings",
                "localField": "meeting_id",
                "foreignField": "_id",
                "as": "m",
            }
        },
        {"$unwind": "$m"},
        {"$group": {"_id": "$meeting_id", "start": {"$first": "$m.start_time"}}},
        {"$sort": {"start": -1}},
        {"$skip": skip},
        {"$limit": page_size},
    ]
    mid_rows = await db.action_items.aggregate(pipe_mids).to_list(None)
    mids = [r["_id"] for r in mid_rows]
    if not mids:
        return [], total_meetings, total_pending_items

    pipeline = [
        {"$match": {"status": st, "meeting_id": {"$in": mids}}},
        {
            "$lookup": {
                "from": "meetings",
                "localField": "meeting_id",
                "foreignField": "_id",
                "as": "m",
            }
        },
        {"$unwind": "$m"},
    ]
    rows = await db.action_items.aggregate(pipeline).to_list(None)
    order_index = {mid: i for i, mid in enumerate(mids)}
    flat: list[dict] = []
    for row in rows:
        m = row["m"]
        flat.append(
            {
                **{k: v for k, v in row.items() if k != "m"},
                "meeting_title": m["title"],
                "meeting_start_time": m["start_time"],
            }
        )

    def sort_key(r: dict) -> tuple:
        mid = r["meeting_id"]
        oid = order_index.get(mid, 10_000)
        return (oid, r.get("confidence", 0), str(r.get("created_at") or ""))

    flat.sort(key=sort_key)
    return flat, total_meetings, total_pending_items


async def list_pending_review_for_meeting(meeting_id: str) -> tuple[list[dict], int]:
    """All pending-review action items for one meeting, with meeting_title / meeting_start_time."""
    try:
        mid = ObjectId(meeting_id)
    except InvalidId as e:
        raise HTTPException(status_code=404, detail="Meeting not found") from e
    db = get_db()
    meeting = await db.meetings.find_one({"_id": mid})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    st = ActionItemStatus.PENDING_REVIEW.value
    cursor = db.action_items.find({"meeting_id": mid, "status": st}).sort(
        [("confidence", 1), ("created_at", 1)]
    )
    docs = await cursor.to_list(None)
    title = meeting["title"]
    start = meeting["start_time"]
    rows: list[dict] = []
    for doc in docs:
        rows.append(
            {
                **doc,
                "meeting_title": title,
                "meeting_start_time": start,
            }
        )
    return rows, len(rows)
