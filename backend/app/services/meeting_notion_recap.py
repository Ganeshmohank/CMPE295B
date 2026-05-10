"""
Post-meeting Notion recap: narrative + action item checklist under a parent page.

Triggered after station-alpha finishes transcript + extraction (HTTP), after action-item
approval (single, bulk, or PATCH to approved), or manually via POST /notion-recap.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from app.config import settings
from app.db import get_db
from app.services.notion_mcp import notion_mcp, NotionMCPError

logger = logging.getLogger(__name__)


def _parse_mid(meeting_id: str) -> ObjectId:
    try:
        return ObjectId(meeting_id)
    except InvalidId as e:
        raise HTTPException(status_code=404, detail="Meeting not found") from e


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


async def _llm_meeting_narrative(
    meeting_title: str,
    transcript_excerpt: str,
    action_lines: list[str],
) -> str:
    if not settings.openai_configured:
        return ""

    items_block = "\n".join(f"- {x}" for x in action_lines[:25]) if action_lines else "(none extracted)"

    prompt = f"""Write a concise internal meeting recap for Notion (plain text, no markdown).
Meeting title: {meeting_title}

Extracted action items:
{items_block}

Transcript excerpt:
{_clip(transcript_excerpt, 12000)}

Instructions:
- 3–6 short paragraphs OR tight bullet groups (your choice).
- Capture themes, decisions, ownership hints, and what the team is pushing on — not a transcript dump.
- If the transcript is thin, lean on the action items list.
- No fluff, no "In conclusion", no marketing tone."""

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 900,
            },
            timeout=60.0,
        )
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()


def _fallback_narrative(meeting_title: str, transcript_excerpt: str, action_lines: list[str]) -> str:
    parts = [
        f"Meeting: {meeting_title}",
        "",
        f"Captured {len(action_lines)} action item(s) for review.",
        "",
        "Transcript preview:",
        _clip(transcript_excerpt, 2500) or "(no transcript text)",
    ]
    return "\n".join(parts)


async def post_meeting_notion_recap(
    meeting_id: str, *, force: bool = False, after_approval: bool = False
) -> dict[str, Any]:
    """
    Create or skip a Notion child page with recap + action bullets.
    Returns { posted, notion_url?, page_id?, skipped_reason?, mock? }.

    ``after_approval`` bypasses ``NOTION_POST_RECAP_AFTER_PROCESSING`` so recap still runs
    when reviewers approve items even if automatic post-ingest posting is turned off.
    """
    oid = _parse_mid(meeting_id)
    db = get_db()
    meeting = await db.meetings.find_one({"_id": oid})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if (
        not settings.notion_post_recap_after_processing
        and not force
        and not after_approval
    ):
        return {"posted": False, "skipped_reason": "notion_post_recap_after_processing is disabled"}

    if not notion_mcp.recap_live and settings.mcp_mode != "live":
        return {"posted": False, "skipped_reason": "MCP_MODE is mock or Notion recap not configured"}

    if not notion_mcp.recap_live:
        return {
            "posted": False,
            "skipped_reason": (
                "Set NOTION_API_KEY plus NOTION_DATABASE_ID and/or NOTION_MEETING_NOTES_PARENT_ID "
                "(share the page or database with your Notion integration)"
            ),
        }

    existing = meeting.get("notion_recap") or {}
    if existing.get("page_id") and not force:
        return {
            "posted": False,
            "skipped_reason": "already_posted",
            "notion_url": existing.get("url"),
            "page_id": existing.get("page_id"),
        }

    transcript = await db.transcripts.find_one({"meeting_id": oid})
    raw = (transcript.get("raw_text") if transcript else "") or ""

    items = (
        await db.action_items.find({"meeting_id": oid}).sort("created_at", 1).to_list(None)
    )
    action_lines: list[str] = []
    for it in items:
        desc = (it.get("description") or "").strip()
        if not desc:
            continue
        owner = (it.get("owner_name") or "").strip()
        pr = (it.get("priority") or "").strip()
        tail = f" — {owner}" if owner else ""
        prf = f"[{pr}] " if pr else ""
        action_lines.append(f"{prf}{desc}{tail}")

    title = (meeting.get("title") or "Meeting").strip()
    st = meeting.get("start_time")
    date_s = ""
    if st is not None:
        if hasattr(st, "strftime"):
            date_s = st.strftime("%Y-%m-%d")
        else:
            date_s = str(st)[:10]
    page_title = f"Recap: {title}" + (f" ({date_s})" if date_s else "")

    narrative = await _llm_meeting_narrative(title, raw, action_lines)
    if not narrative.strip():
        narrative = _fallback_narrative(title, raw, action_lines)

    sections: list[tuple[str, str]] = [
        ("Overview", narrative),
    ]
    meta_bits = [
        f"Action items captured: {len(action_lines)}",
        f"Transcript chars: {len(raw)}",
    ]
    if meeting.get("zoom_meeting_id"):
        meta_bits.append(f"Zoom meeting id: {meeting['zoom_meeting_id']}")
    sections.insert(0, ("Meeting intelligence", "\n".join(meta_bits)))

    bullets: list[tuple[str, list[str]]] = []
    if action_lines:
        bullets.append(("Action items (pending review)", action_lines))

    try:
        result = await notion_mcp.create_meeting_recap_page(
            page_title=page_title,
            section_heading_to_paragraphs=sections,
            bullet_sections=bullets or None,
        )
    except NotionMCPError as e:
        return {"posted": False, "skipped_reason": f"notion_error: {str(e)}"}

    pid = result.get("id")
    url = (result.get("url") or "").strip()
    if pid and not url:
        hex_id = str(pid).replace("-", "")
        if len(hex_id) == 32:
            url = f"https://www.notion.so/{hex_id}"
    now = datetime.now(timezone.utc)
    recap_doc = {"page_id": pid, "url": url, "posted_at": now}

    await db.meetings.update_one(
        {"_id": oid},
        {"$set": {"notion_recap": recap_doc, "updated_at": now}},
    )

    await db.processing_logs.insert_one(
        {
            "meeting_id": oid,
            "stage": "notion_recap",
            "status": "success",
            "message": f"Posted meeting recap to Notion ({len(action_lines)} action items listed)",
            "processing_time_ms": None,
            "timestamp": now,
        }
    )

    out: dict[str, Any] = {
        "posted": True,
        "notion_url": url,
        "page_id": pid,
        "mock": result.get("mock", False),
    }
    return out


async def _post_notion_recap_after_approval_safe(meeting_id: str) -> None:
    """Background task: attempt recap after approval; errors are logged only."""
    try:
        await post_meeting_notion_recap(meeting_id, force=False, after_approval=True)
    except HTTPException as e:
        logger.warning(
            "Notion recap after approval failed (meeting=%s): %s",
            meeting_id,
            e.detail,
        )
    except Exception:
        logger.exception("Notion recap after approval failed (meeting=%s)", meeting_id)


def schedule_notion_recap_after_approval(meeting_id: str) -> None:
    """Fire-and-forget recap when items are approved (skipped if already posted or Notion off)."""
    mid = (meeting_id or "").strip()
    if not mid:
        return
    asyncio.create_task(_post_notion_recap_after_approval_safe(mid))


def verify_internal_secret(provided: str | None) -> None:
    expected = (settings.internal_api_secret or "").strip()
    if not expected:
        return
    if (provided or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret")
