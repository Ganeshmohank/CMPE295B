"""Re-run action-item extraction from an existing transcript (OpenAI), mirroring station-alpha."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx
from bson import ObjectId
from bson.errors import InvalidId

from app.config import settings
from app.db import get_db
from app.services.meeting_context import merge_meeting_display_context

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert meeting analyst. You receive a meeting transcript and optional meeting context.

Extract action items that belong in a task tracker.

Rules:
- Use meeting context ONLY to resolve ambiguous references (people, initiative names, jargon). Do NOT invent tasks from context alone—every item must be clearly grounded in the transcript.
- Include ONLY concrete, actionable tasks: explicit commitments, assignments, or strongly agreed next steps with a discernible deliverable.
- EXCLUDE vague brainstorming ("maybe we should…"), unclear obligations, topics with no specific action, generic discussion, or anything you cannot phrase as a concrete task.
- If you are unsure whether something qualifies, omit it.
- dueDate must be an ISO calendar date YYYY-MM-DD only when an explicit calendar date appears in the transcript (or context quotes one verbatim). Otherwise use an empty string. Never output relative phrases like "tomorrow", "next week", or "end of month".

For each kept action item, identify:
- The task description (text)
- Who it's assigned to (assignee, or empty string)
- dueDate (YYYY-MM-DD or empty string)

You MUST respond with valid JSON only, using this exact shape:
{"actionItems":[{"text":"","assignee":"","dueDate":""}]}
Use an empty array for actionItems if there are none."""


_MIN_ACTION_DESCRIPTION_LEN = 15

_VAGUE_OPENERS = (
    "maybe ",
    "perhaps ",
    "we might ",
    "might be nice",
    "consider ",
    "think about ",
    "not sure ",
    "unclear ",
    "tbd",
    "someone should ",
    "need to discuss ",
    "figure out later",
)


def _item_description_raw(item: dict[str, Any]) -> str:
    raw = item.get("text") or item.get("description") or item.get("task") or ""
    return str(raw).strip()


def _is_clear_action_description(description: str) -> bool:
    if len(description) < _MIN_ACTION_DESCRIPTION_LEN:
        return False
    low = description.lower().strip()
    generic = {"action item", "follow up", "follow-up", "todo", "task", "next steps"}
    if low in generic:
        return False
    for phrase in _VAGUE_OPENERS:
        if low.startswith(phrase):
            return False
    return True


def _filter_and_dedupe_extracted(items: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        desc = _item_description_raw(raw)
        if not _is_clear_action_description(desc):
            continue
        key = desc.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(raw)
    return out


def _normalize_due_date_storage(raw: Any) -> str | None:
    """Persist only valid YYYY-MM-DD; ignore relative / fuzzy phrases."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    head = s[:10]
    if len(head) == 10 and head[4] == "-" and head[7] == "-":
        try:
            date.fromisoformat(head)
            return head
        except ValueError:
            return None
    return None


async def _meeting_context_prompt_block(meeting: dict[str, Any]) -> str:
    merged = await merge_meeting_display_context(meeting)
    parts: list[str] = []
    pt = merged.get("project_theme")
    if isinstance(pt, str) and pt.strip():
        parts.append(f"Project / initiative: {pt.strip()}")
    dev = merged.get("context_developer")
    if isinstance(dev, str) and dev.strip():
        parts.append(f"Engineering / technical context:\n{dev.strip()}")
    pm = merged.get("context_pm")
    if isinstance(pm, str) and pm.strip():
        parts.append(f"PM / stakeholder context:\n{pm.strip()}")
    return "\n\n".join(parts)


def _build_user_prompt(topic: str, transcript: str, context_block: str) -> str:
    chunks = [f"Meeting title: {topic}"]
    if context_block.strip():
        chunks.append(
            "--- Meeting context (resolve ambiguity only; do not invent tasks from here) ---\n"
            + context_block.strip()
        )
    chunks.append("--- Transcript ---\n" + transcript)
    return "\n\n".join(chunks)


async def extract_action_items_llm(
    transcript: str, meeting_topic: str, *, context_block: str = ""
) -> list[dict[str, Any]]:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")
    user_content = _build_user_prompt(meeting_topic, transcript, context_block)
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
    except httpx.HTTPError as e:
        logger.warning("OpenAI extraction HTTP error: %s", e)
        raise ValueError(f"OpenAI request failed: {e}") from e

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        logger.warning("OpenAI extraction response missing content: %s", data)
        raise ValueError("OpenAI returned an unexpected response") from e
    if not isinstance(content, str) or not content.strip():
        logger.warning("OpenAI extraction response had empty content: %s", data)
        raise ValueError("OpenAI returned an empty response")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError("OpenAI returned invalid JSON") from e
    items = (
        parsed.get("actionItems")
        or parsed.get("items")
        or parsed.get("action_items")
        or (parsed if isinstance(parsed, list) else [])
    )
    return items if isinstance(items, list) else []


async def re_extract_action_items_for_meeting(meeting_id: str) -> dict[str, Any]:
    """Replace action_items for this meeting from transcript text; append processing_logs row."""
    try:
        oid = ObjectId(meeting_id.strip())
    except InvalidId as e:
        raise ValueError("Invalid meeting id") from e

    db = get_db()
    meeting = await db.meetings.find_one({"_id": oid})
    if not meeting:
        raise ValueError("Meeting not found")

    transcript = await db.transcripts.find_one({"meeting_id": oid})
    raw_text = (transcript or {}).get("raw_text") or ""
    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("No transcript text to extract from")

    t0 = time.perf_counter()
    topic = meeting.get("title") or "Untitled Meeting"
    ctx = await _meeting_context_prompt_block(meeting)
    extracted_raw = await extract_action_items_llm(raw_text, topic, context_block=ctx)
    extracted = _filter_and_dedupe_extracted(extracted_raw)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    t = datetime.now(timezone.utc)
    await db.action_items.delete_many({"meeting_id": oid})

    for item in extracted:
        raw = item.get("text") or item.get("description") or item.get("task") or ""
        desc = str(raw).strip() or "Action item"
        assignee = item.get("assignee") or item.get("owner") or item.get("owner_name") or ""
        owner_name = str(assignee).strip() or None
        due_raw = item.get("dueDate") or item.get("due_date")
        due = _normalize_due_date_storage(due_raw)

        await db.action_items.insert_one(
            {
                "meeting_id": oid,
                "description": desc,
                "owner_name": owner_name,
                "due_date": due,
                "priority": "medium",
                "confidence": 0.82,
                "status": "pending_review",
                "source_snippet": desc[:280],
                "created_at": t,
                "updated_at": t,
            }
        )

    await db.meetings.update_one(
        {"_id": oid},
        {
            "$set": {
                "status": "completed",
                "processing_status": "processed",
                "updated_at": t,
            }
        },
    )

    base_msg = (
        f'Extracted {len(extracted)} action item(s) from "{topic}" '
        f'(manual re-run; replaced prior items for this meeting)'
    )
    await db.processing_logs.insert_one(
        {
            "meeting_id": oid,
            "stage": "extraction",
            "status": "success",
            "message": base_msg,
            "processing_time_ms": elapsed_ms,
            "timestamp": t,
        }
    )

    return {"extracted_count": len(extracted), "processing_time_ms": elapsed_ms}
