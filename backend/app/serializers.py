from datetime import date, datetime
from typing import Any

from bson import ObjectId

from app.schemas.common import oid_str


def _parse_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    return None


def transcript_to_out(doc: dict) -> dict:
    return {
        "id": oid_str(doc["_id"]),
        "meeting_id": oid_str(doc["meeting_id"]),
        "raw_text": doc["raw_text"],
        "segments": doc.get("segments"),
        "transcript_length": doc["transcript_length"],
        "created_at": doc["created_at"],
    }


def action_item_to_out(doc: dict) -> dict:
    return {
        "id": oid_str(doc["_id"]),
        "meeting_id": oid_str(doc["meeting_id"]),
        "description": doc["description"],
        "owner_name": doc.get("owner_name"),
        "due_date": _parse_date(doc.get("due_date")),
        "priority": doc["priority"],
        "confidence": doc["confidence"],
        "status": doc["status"],
        "source_snippet": doc.get("source_snippet"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def processing_log_to_out(doc: dict) -> dict:
    return {
        "id": oid_str(doc["_id"]),
        "meeting_id": oid_str(doc["meeting_id"]),
        "stage": doc["stage"],
        "status": doc["status"],
        "message": doc["message"],
        "processing_time_ms": doc.get("processing_time_ms"),
        "timestamp": doc["timestamp"],
    }


def meeting_to_metadata(doc: dict, merged_context: dict | None = None) -> dict:
    ctx = merged_context or {
        "project_id": (
            oid_str(doc["project_id"]) if isinstance(doc.get("project_id"), ObjectId) else None
        ),
        "project_theme": doc.get("project_theme"),
        "context_developer": doc.get("context_developer"),
        "context_pm": doc.get("context_pm"),
    }
    return {
        "id": oid_str(doc["_id"]),
        "title": doc["title"],
        "source": doc["source"],
        "start_time": doc["start_time"],
        "duration_minutes": doc["duration_minutes"],
        "status": doc["status"],
        "processing_status": doc["processing_status"],
        "participants_count": doc.get("participants_count", 0),
        "project_id": ctx.get("project_id"),
        "project_theme": ctx.get("project_theme"),
        "context_developer": ctx.get("context_developer"),
        "context_pm": ctx.get("context_pm"),
    }


def action_item_review_row(doc: dict) -> dict:
    base = action_item_to_out(doc)
    base["meeting_title"] = doc["meeting_title"]
    base["meeting_start_time"] = doc["meeting_start_time"]
    return base


def action_item_review_detail_row(doc: dict) -> dict:
    base = action_item_review_row(doc)
    base["participants"] = doc["participants"]
    base["processing_logs"] = [processing_log_to_out(l) for l in doc["processing_logs"]]
    return base
