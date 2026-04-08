import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db import get_db
from app.schemas.dashboard import DashboardSummary, MeetingsListPageOut, MeetingsListSummary
from app.schemas.meeting import MeetingListItem, ProjectThemesOut
from app.services.dashboard_metrics import (
    compute_dashboard_summary,
    meetings_list_paginated,
    meetings_list_summary,
)

router = APIRouter()


@router.get("/project-themes", response_model=ProjectThemesOut)
async def list_project_themes(
    q: str | None = Query(None, description="Optional substring filter (case-insensitive)"),
) -> ProjectThemesOut:
    """Distinct project_theme values across meetings (initiative autocomplete)."""
    db = get_db()
    filt: dict = {
        "$and": [
            {"project_theme": {"$exists": True}},
            {"project_theme": {"$nin": [None, ""]}},
        ]
    }
    if q and q.strip():
        filt["$and"].append(
            {"project_theme": {"$regex": re.escape(q.strip()), "$options": "i"}}
        )
    cat_filt: dict = {}
    if q and q.strip():
        cat_filt = {"name": {"$regex": re.escape(q.strip()), "$options": "i"}}
    from_catalog = await db.projects.distinct("name", cat_filt)
    raw_meetings = await db.meetings.distinct("project_theme", filt)
    themes = sorted(
        {t for t in from_catalog if isinstance(t, str) and t.strip()}
        | {t for t in raw_meetings if isinstance(t, str) and t.strip()},
        key=str.casefold,
    )
    return ProjectThemesOut(themes=themes[:200])


def _coerce_int_optional(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if isinstance(v, float):
        return int(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_window_days_param(raw: str | None) -> int:
    """Parse query string so '7' / '30' always work (no Pydantic Literal on query params)."""
    s = (raw or "7").strip()
    try:
        n = int(s)
    except ValueError:
        raise HTTPException(status_code=422, detail="window_days must be 7 or 30") from None
    if n not in (7, 30):
        raise HTTPException(status_code=422, detail="window_days must be 7 or 30")
    return n


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    window_days: str | None = Query(
        default="7",
        description="Rolling window for in-window counts: 7 or 30",
    ),
) -> DashboardSummary:
    wd = _parse_window_days_param(window_days)
    data = await compute_dashboard_summary(window_days=wd)
    return DashboardSummary(**data)


_MEETINGS_SORT = frozenset(
    {"date_desc", "date_asc", "title", "actions_desc", "pending_first"}
)


@router.get("/meetings", response_model=MeetingsListPageOut)
async def dashboard_meetings_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=10),
    q: str | None = Query(None, description="Substring match on title or source"),
    pipeline: str | None = Query(
        None,
        description="Meetings.processing_status, or omit / 'all' for any",
    ),
    focus_pending: bool = Query(False, description="Only meetings with pending_review action items"),
    sort: str = Query(
        "date_desc",
        description="date_desc | date_asc | title | actions_desc | pending_first",
    ),
) -> MeetingsListPageOut:
    sort_key = sort if sort in _MEETINGS_SORT else "date_desc"
    proc = (pipeline or "").strip()
    if proc.lower() in ("", "all"):
        proc_f: str | None = None
    else:
        proc_f = proc

    rows_task = meetings_list_paginated(
        page=page,
        page_size=page_size,
        q=q,
        processing_status=proc_f,
        focus_pending=focus_pending,
        sort=sort_key,
    )
    summary_task = meetings_list_summary()
    (rows, total), summary = await asyncio.gather(rows_task, summary_task)

    items = [
        MeetingListItem(
            id=str(r["_id"]),
            title=r["title"],
            source=r.get("source", "zoom"),
            date=r["start_time"],
            duration_minutes=int(r.get("duration_minutes", 0)),
            status=r["status"],
            processing_status=r["processing_status"],
            participants_count=r.get("participants_count", 0),
            action_items_count=r.get("action_items_count", 0),
            pending_review_count=int(r.get("pending_review_count", 0)),
            transcript_length=_coerce_int_optional(r.get("transcript_length")),
        )
        for r in rows
    ]
    return MeetingsListPageOut(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        summary=MeetingsListSummary(**summary),
    )
