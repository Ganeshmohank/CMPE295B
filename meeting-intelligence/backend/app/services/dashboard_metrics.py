import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import get_db
from app.domain.enums import ActionItemStatus, ProcessingStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _meeting_ids_started_since(db: Any, since: datetime) -> list[Any]:
    cursor = db.meetings.find({"start_time": {"$gte": since}}, {"_id": 1})
    return [doc["_id"] async for doc in cursor]


async def _count_by_field(collection: str, field: str) -> dict[str, int]:
    db = get_db()
    cursor = db[collection].aggregate(
        [{"$group": {"_id": f"${field}", "c": {"$sum": 1}}}]
    )
    out: dict[str, int] = {}
    async for doc in cursor:
        k = doc["_id"]
        if k is not None:
            out[str(k)] = int(doc["c"])
    return out


async def compute_dashboard_summary(
    window_days: int = 7,
) -> dict:
    """Aggregates many collection stats; runs independent queries concurrently to cut latency."""
    db = get_db()
    now = _utcnow()
    window_start = now - timedelta(days=window_days)
    pr = ActionItemStatus.PENDING_REVIEW.value

    async def agg_seats() -> int:
        cur = db.meetings.aggregate(
            [{"$group": {"_id": None, "t": {"$sum": "$participants_count"}}}]
        )
        docs = await cur.to_list(1)
        return int(docs[0]["t"]) if docs else 0

    async def agg_tlen() -> float | None:
        cur = db.transcripts.aggregate(
            [{"$group": {"_id": None, "avg": {"$avg": "$transcript_length"}}}]
        )
        docs = await cur.to_list(1)
        return (
            float(docs[0]["avg"])
            if docs and docs[0].get("avg") is not None
            else None
        )

    async def agg_pconf() -> float | None:
        cur = db.action_items.aggregate(
            [
                {"$match": {"status": pr}},
                {"$group": {"_id": None, "avg": {"$avg": "$confidence"}}},
            ]
        )
        docs = await cur.to_list(1)
        return (
            float(docs[0]["avg"])
            if docs and docs[0].get("avg") is not None
            else None
        )

    async def agg_proc_ms() -> float | None:
        cur = db.processing_logs.aggregate(
            [
                {"$match": {"processing_time_ms": {"$ne": None, "$exists": True}}},
                {"$group": {"_id": None, "avg": {"$avg": "$processing_time_ms"}}},
            ]
        )
        docs = await cur.to_list(1)
        return (
            float(docs[0]["avg"])
            if docs and docs[0].get("avg") is not None
            else None
        )

    meeting_ids_task = _meeting_ids_started_since(db, window_start)

    (
        total_meetings,
        total_processed_meetings,
        total_transcripts,
        total_action_items,
        total_pending_reviews,
        total_failed_pipelines,
        pipelines_in_progress,
        pipelines_not_started,
        meetings_in_window,
        pending_low_confidence,
        action_items_approved_or_ticketed,
        action_items_rejected,
        terminal,
        meeting_ids_window,
        total_participant_seats,
        avg_transcript_length,
        pending_review_avg_confidence,
        average_processing_time_ms,
        meetings_by_processing_status,
        meetings_by_meeting_status,
        action_items_by_status,
    ) = await asyncio.gather(
        db.meetings.count_documents({}),
        db.meetings.count_documents({"processing_status": ProcessingStatus.PROCESSED.value}),
        db.transcripts.count_documents({}),
        db.action_items.count_documents({}),
        db.action_items.count_documents({"status": pr}),
        db.meetings.count_documents({"processing_status": ProcessingStatus.FAILED.value}),
        db.meetings.count_documents({"processing_status": ProcessingStatus.IN_PROGRESS.value}),
        db.meetings.count_documents({"processing_status": ProcessingStatus.NOT_STARTED.value}),
        db.meetings.count_documents({"start_time": {"$gte": window_start}}),
        db.action_items.count_documents({"status": pr, "confidence": {"$lt": 0.65}}),
        db.action_items.count_documents(
            {
                "status": {
                    "$in": [
                        ActionItemStatus.APPROVED.value,
                        ActionItemStatus.TICKET_CREATED.value,
                    ]
                }
            }
        ),
        db.action_items.count_documents({"status": ActionItemStatus.REJECTED.value}),
        db.meetings.count_documents(
            {
                "processing_status": {
                    "$in": [ProcessingStatus.PROCESSED.value, ProcessingStatus.FAILED.value]
                }
            }
        ),
        meeting_ids_task,
        agg_seats(),
        agg_tlen(),
        agg_pconf(),
        agg_proc_ms(),
        _count_by_field("meetings", "processing_status"),
        _count_by_field("meetings", "status"),
        _count_by_field("action_items", "status"),
    )

    if meeting_ids_window:
        action_items_in_window = await db.action_items.count_documents(
            {"meeting_id": {"$in": meeting_ids_window}}
        )
    else:
        action_items_in_window = 0

    avg_action_items_per_meeting = (
        total_action_items / total_meetings if total_meetings else None
    )
    reviewed = action_items_approved_or_ticketed + action_items_rejected
    human_review_throughput_rate = (
        action_items_approved_or_ticketed / reviewed if reviewed else None
    )
    success_rate = total_processed_meetings / terminal if terminal else None
    tickets_created = action_items_by_status.get(ActionItemStatus.TICKET_CREATED.value, 0)

    return {
        "total_meetings": total_meetings,
        "total_processed_meetings": total_processed_meetings,
        "total_transcripts": total_transcripts,
        "total_action_items": total_action_items,
        "total_pending_reviews": total_pending_reviews,
        "total_failed_pipelines": total_failed_pipelines,
        "average_processing_time_ms": average_processing_time_ms,
        "success_rate": success_rate,
        "window_days": window_days,
        "meetings_in_window": meetings_in_window,
        "action_items_in_window": action_items_in_window,
        "pending_review_low_confidence": pending_low_confidence,
        "action_items_ticket_created": tickets_created,
        "pipelines_in_progress": pipelines_in_progress,
        "pipelines_not_started": pipelines_not_started,
        "total_participant_seats": total_participant_seats,
        "avg_action_items_per_meeting": avg_action_items_per_meeting,
        "avg_transcript_length": avg_transcript_length,
        "pending_review_avg_confidence": pending_review_avg_confidence,
        "action_items_approved_or_ticketed": action_items_approved_or_ticketed,
        "action_items_rejected": action_items_rejected,
        "human_review_throughput_rate": human_review_throughput_rate,
        "meetings_by_processing_status": meetings_by_processing_status,
        "meetings_by_meeting_status": meetings_by_meeting_status,
        "action_items_by_status": action_items_by_status,
    }


async def meetings_with_action_counts() -> list[dict]:
    db = get_db()
    pipeline = [
        {
            "$lookup": {
                "from": "action_items",
                "localField": "_id",
                "foreignField": "meeting_id",
                "as": "items",
            }
        },
        {
            "$lookup": {
                "from": "transcripts",
                "localField": "_id",
                "foreignField": "meeting_id",
                "as": "tr",
            }
        },
        {
            "$addFields": {
                "action_items_count": {"$size": "$items"},
                "pending_review_count": {
                    "$size": {
                        "$filter": {
                            "input": "$items",
                            "as": "it",
                            "cond": {
                                "$eq": [
                                    "$$it.status",
                                    ActionItemStatus.PENDING_REVIEW.value,
                                ]
                            },
                        }
                    }
                },
                "transcript_length": {
                    "$cond": [
                        {"$gt": [{"$size": "$tr"}, 0]},
                        {
                            "$let": {
                                "vars": {
                                    "firstTr": {"$arrayElemAt": ["$tr", 0]},
                                },
                                "in": "$$firstTr.transcript_length",
                            }
                        },
                        None,
                    ]
                },
            }
        },
        {"$project": {"items": 0, "tr": 0}},
        {"$sort": {"start_time": -1}},
    ]
    cursor = db.meetings.aggregate(pipeline)
    return await cursor.to_list(None)


async def meetings_list_summary() -> dict[str, int]:
    """Lightweight aggregates for meetings list KPIs (no per-meeting joins)."""
    db = get_db()
    tm = await db.meetings.count_documents({})
    tai = await db.action_items.count_documents({})
    tpr = await db.action_items.count_documents(
        {"status": ActionItemStatus.PENDING_REVIEW.value}
    )
    seats_cur = db.meetings.aggregate(
        [{"$group": {"_id": None, "t": {"$sum": "$participants_count"}}}]
    )
    seats_docs = await seats_cur.to_list(1)
    tseats = int(seats_docs[0]["t"]) if seats_docs else 0
    return {
        "all_meetings": tm,
        "all_action_items": tai,
        "all_pending_review": tpr,
        "all_participant_seats": tseats,
    }


def _meetings_list_sort(sort: str) -> dict[str, int]:
    m = {
        "date_desc": {"start_time": -1},
        "date_asc": {"start_time": 1},
        "title": {"title": 1},
        "actions_desc": {"action_items_count": -1, "start_time": -1},
        "pending_first": {"pending_review_count": -1, "start_time": -1},
    }
    return m.get(sort, m["date_desc"])


async def meetings_list_paginated(
    *,
    page: int,
    page_size: int,
    q: str | None,
    processing_status: str | None,
    focus_pending: bool,
    sort: str,
) -> tuple[list[dict], int]:
    """Filter/sort meetings with action-item counts; return one page + total matching count."""
    db = get_db()
    page = max(1, page)
    page_size = max(1, min(10, page_size))
    skip = (page - 1) * page_size

    stages: list[dict[str, Any]] = []
    early: dict[str, Any] = {}
    if q and q.strip():
        esc = re.escape(q.strip())
        early["$or"] = [
            {"title": {"$regex": esc, "$options": "i"}},
            {"source": {"$regex": esc, "$options": "i"}},
        ]
    if processing_status and processing_status.strip().lower() not in ("", "all"):
        early["processing_status"] = processing_status.strip()
    if early:
        stages.append({"$match": early})

    stages.extend(
        [
            {
                "$lookup": {
                    "from": "action_items",
                    "localField": "_id",
                    "foreignField": "meeting_id",
                    "as": "items",
                }
            },
            {
                "$lookup": {
                    "from": "transcripts",
                    "localField": "_id",
                    "foreignField": "meeting_id",
                    "as": "tr",
                }
            },
            {
                "$addFields": {
                    "action_items_count": {"$size": "$items"},
                    "pending_review_count": {
                        "$size": {
                            "$filter": {
                                "input": "$items",
                                "as": "it",
                                "cond": {
                                    "$eq": [
                                        "$$it.status",
                                        ActionItemStatus.PENDING_REVIEW.value,
                                    ]
                                },
                            }
                        }
                    },
                    "transcript_length": {
                        "$cond": [
                            {"$gt": [{"$size": "$tr"}, 0]},
                            {
                                "$let": {
                                    "vars": {"firstTr": {"$arrayElemAt": ["$tr", 0]}},
                                    "in": "$$firstTr.transcript_length",
                                }
                            },
                            None,
                        ]
                    },
                }
            },
            {"$project": {"items": 0, "tr": 0}},
        ]
    )
    if focus_pending:
        stages.append({"$match": {"pending_review_count": {"$gt": 0}}})

    stages.append({"$sort": _meetings_list_sort(sort)})
    stages.append(
        {
            "$facet": {
                "meta": [{"$count": "total"}],
                "data": [{"$skip": skip}, {"$limit": page_size}],
            }
        }
    )

    cursor = db.meetings.aggregate(stages)
    chunk = await cursor.to_list(1)
    if not chunk:
        return [], 0
    block = chunk[0]
    total = int(block["meta"][0]["total"]) if block.get("meta") else 0
    return block.get("data") or [], total
