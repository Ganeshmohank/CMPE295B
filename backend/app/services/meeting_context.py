"""Resolve project/initiative text for meetings (project document + optional meeting overrides)."""

from typing import Any

from bson import ObjectId

from app.db import get_db
from app.schemas.common import oid_str


async def merge_meeting_display_context(meeting: dict[str, Any]) -> dict[str, Any]:
    """
    Effective project_theme / context_developer / context_pm for API responses.
    Meeting may store overrides; omitted/null fields inherit from linked `projects` doc.
    Legacy meetings use only embedded fields (no project_id).
    """
    db = get_db()
    proj: dict[str, Any] | None = None
    pid = meeting.get("project_id")
    if isinstance(pid, ObjectId):
        proj = await db.projects.find_one({"_id": pid})

    theme = meeting.get("project_theme")
    if theme is None and proj:
        theme = proj.get("name")

    dev = meeting.get("context_developer")
    if dev is None and proj:
        dev = proj.get("context_developer")

    pm = meeting.get("context_pm")
    if pm is None and proj:
        pm = proj.get("context_pm")

    return {
        "project_id": oid_str(pid) if isinstance(pid, ObjectId) else None,
        "project_theme": theme,
        "context_developer": dev,
        "context_pm": pm,
    }
