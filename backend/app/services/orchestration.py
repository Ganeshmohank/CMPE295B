"""
Orchestration Service - Manages automated workflows for action items.

Uses:
- Jira for work items (issues, transitions, comments, epics)
- Confluence for documentation page comments
- LLM classifier to determine action types
- Execution logs for audit trail
"""

import asyncio
import re
from datetime import datetime, timedelta, timezone, time

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from app.config import settings
from app.db import get_db
from app.services.meetings import count_meeting_participant_links, list_meeting_attendee_emails
from app.services.invite_recipients import partition_invite_recipients
from app.services.participant_email import send_participant_digest, smtp_configured
from app.services.calendar_business_time import move_weekend_to_monday
from app.services.jira_mcp import jira_mcp, JiraMCPError
from app.services.confluence_mcp import confluence_mcp, ConfluenceMCPError
from app.services.action_classifier import (
    classify_action_item,
    ActionClassification,
    OrchestrationAction as ClassifierAction,
    TicketType,
)
from app.schemas.orchestration import (
    ExecutionLogCreate,
    OrchestrationAction,
    OrchestrationStatus,
)

_SCHEDULE_CUE_RE = re.compile(
    r"\b(tomorrow|today|tonight|next\s+(?:day|week)|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"morning|afternoon|noon|midnight|"
    r"\d{1,2}\s*[:.]\s*\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)?|"
    r"\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.)|"
    r"at\s+\d{1,2})\b",
    re.I,
)


def combined_schedule_text(description: str, source_snippet: str | None) -> str:
    parts: list[str] = []
    if description and description.strip():
        parts.append(description.strip())
    if source_snippet and source_snippet.strip():
        parts.append(source_snippet.strip())
    return "\n".join(parts)


def text_has_meeting_time_cue(text: str) -> bool:
    return bool(text.strip()) and bool(_SCHEDULE_CUE_RE.search(text))


def derive_calendar_event_title(action_item_doc: dict, meeting_doc: dict | None) -> str:
    d = (action_item_doc.get("description") or "").strip()
    if d:
        line = d.split("\n")[0].strip()
        return (line[:100] + "…") if len(line) > 100 else line
    mt = (meeting_doc or {}).get("title") if meeting_doc else None
    return (mt or "Meeting").strip()[:100]


def _calendar_invite_summary(invite_mode: str, attendee_count: int) -> str:
    if invite_mode == "sent":
        return f"Google emailed calendar invites to {attendee_count} recipient(s) (sendUpdates)."
    if invite_mode == "description_only":
        return (
            "Event created; invites were not emailed — attendee addresses were added to the "
            "description (typical for service accounts without Workspace delegation / OAuth)."
        )
    if attendee_count == 0:
        return "No invite emails — roster has no participant email addresses."
    return f"Event lists {attendee_count} attendee(s); invite mode: {invite_mode}."


def _parse_preview(text: str | None, max_len: int = 240) -> str | None:
    if not text or not str(text).strip():
        return None
    s = str(text).strip().replace("\n", " ")
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _parse_oid(id_str: str, entity: str = "Item") -> ObjectId:
    try:
        return ObjectId(id_str)
    except InvalidId as e:
        raise HTTPException(status_code=404, detail=f"{entity} not found") from e


async def create_execution_log(log: ExecutionLogCreate) -> dict:
    """Create a new execution log entry."""
    db = get_db()
    doc = {
        "action_item_id": _parse_oid(log.action_item_id, "Action item"),
        "meeting_id": _parse_oid(log.meeting_id, "Meeting"),
        "action": log.action.value,
        "status": log.status.value,
        "message": log.message,
        "details": log.details,
        "triggered_by": log.triggered_by,
        "created_at": datetime.now(timezone.utc),
        "updated_at": None,
    }
    result = await db.execution_logs.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def update_execution_log(
    log_id: str,
    status: OrchestrationStatus,
    message: str,
    details: dict | None = None,
) -> dict:
    """Update an execution log entry."""
    db = get_db()
    oid = _parse_oid(log_id, "Execution log")
    update_doc = {
        "status": status.value,
        "message": message,
        "updated_at": datetime.now(timezone.utc),
    }
    if details is not None:
        update_doc["details"] = details
    await db.execution_logs.update_one({"_id": oid}, {"$set": update_doc})
    return await db.execution_logs.find_one({"_id": oid})


async def get_execution_logs_for_action_item(action_item_id: str) -> list[dict]:
    """Get all execution logs for an action item."""
    db = get_db()
    oid = _parse_oid(action_item_id, "Action item")
    cursor = db.execution_logs.find({"action_item_id": oid}).sort("created_at", -1)
    return await cursor.to_list(None)


async def get_execution_logs_for_meeting(meeting_id: str) -> list[dict]:
    """Get all execution logs for a meeting."""
    db = get_db()
    oid = _parse_oid(meeting_id, "Meeting")
    cursor = db.execution_logs.find({"meeting_id": oid}).sort("created_at", -1)
    return await cursor.to_list(None)


async def build_classification_context(
    meeting_id: ObjectId,
    action_item_id: ObjectId,
    action_item_doc: dict,
) -> tuple[str | None, list[str] | None, str | None, str | None]:
    """Transcript + related action items for LLM orchestration (aligns approve + manual re-trigger)."""
    db = get_db()
    transcript = await db.transcripts.find_one({"meeting_id": meeting_id})
    raw = (transcript.get("raw_text") or "") if transcript else ""
    transcript_context = raw[:50000] if raw.strip() else None

    others = await db.action_items.find(
        {"meeting_id": meeting_id, "_id": {"$ne": action_item_id}}
    ).to_list(12)
    descs = [o.get("description", "") for o in others if o.get("description")]
    other_action_items = descs[:5] if descs else None

    owner_name = action_item_doc.get("owner_name")
    due = action_item_doc.get("due_date")
    due_s: str | None = None
    if due is not None:
        due_s = due.isoformat() if hasattr(due, "isoformat") else str(due)
    return transcript_context, other_action_items, owner_name, due_s


async def execute_create_ticket(
    action_item_id: str,
    meeting_id: str,
    description: str,
    priority: str,
    classification: ActionClassification | None = None,
    source_snippet: str | None = None,
    triggered_by: str = "user",
    meeting_title: str | None = None,
    project_theme: str | None = None,
) -> dict:
    """Create a Jira issue in the configured project."""
    log = await create_execution_log(
        ExecutionLogCreate(
            action_item_id=action_item_id,
            meeting_id=meeting_id,
            action=OrchestrationAction.CREATE_JIRA_TICKET,
            status=OrchestrationStatus.RUNNING,
            message="Creating Jira issue...",
            triggered_by=triggered_by,
        )
    )
    log_id = str(log["_id"])

    try:
        ticket_type = classification.ticket_type.value if classification else "task"

        if classification and classification.extracted_title:
            title = classification.extracted_title
        else:
            title = description[:100] if len(description) > 100 else description

        ticket_description = (
            classification.extracted_description if classification and classification.extracted_description
            else description
        )

        result = await jira_mcp.create_ticket(
            title=title,
            description=ticket_description,
            ticket_type=ticket_type,
            priority=classification.priority if classification else priority,
            status="To Do",
            source_meeting_id=meeting_id,
            source_snippet=source_snippet,
            ticket_body_context=classification.ticket_body_context if classification else None,
            ticket_body_discussion=classification.ticket_body_discussion if classification else None,
            ticket_body_next_steps=classification.ticket_body_next_steps if classification else None,
            meeting_title=meeting_title,
            project_theme=project_theme,
        )

        mode_label = "[Mock] " if result.get("mock") else ""
        key = result.get("key") or result["id"]

        details: dict = {
            "ticket_id": key,
            "issue_key": key,
            "ticket_type": result["type"],
            "priority": result["priority"],
            "url": result["url"],
            "mock": result.get("mock", False),
        }

        if classification:
            if classification.story_points:
                details["story_points"] = classification.story_points
            if classification.assignee:
                details["assignee"] = classification.assignee
            if classification.labels:
                details["labels"] = classification.labels

        message_parts = [f'{mode_label}Created Jira {result["type"]}: "{title[:50]}" ({key})']
        if classification and classification.story_points:
            message_parts.append(f"({classification.story_points} points)")
        if classification and classification.assignee:
            message_parts.append(f"→ {classification.assignee}")

        await update_execution_log(
            log_id,
            OrchestrationStatus.SUCCESS,
            " ".join(message_parts),
            details=details,
        )

    except JiraMCPError as e:
        await update_execution_log(
            log_id,
            OrchestrationStatus.ERROR,
            f"Failed to create Jira issue: {str(e)}",
        )

    return await get_db().execution_logs.find_one({"_id": log["_id"]})


async def execute_link_to_epic(
    action_item_id: str,
    meeting_id: str,
    project_theme: str | None,
    classification: ActionClassification | None = None,
    triggered_by: str = "user",
) -> dict:
    """Find a Jira Epic and link the action item's issue to it (best-effort)."""
    log = await create_execution_log(
        ExecutionLogCreate(
            action_item_id=action_item_id,
            meeting_id=meeting_id,
            action=OrchestrationAction.LINK_TO_EPIC,
            status=OrchestrationStatus.RUNNING,
            message="Finding matching Jira epic...",
            triggered_by=triggered_by,
        )
    )
    log_id = str(log["_id"])

    try:
        epic_name = (
            classification.suggested_epic if classification else None
        ) or project_theme or "General"

        epic = await jira_mcp.find_epic_by_name(epic_name)

        if epic:
            mode_label = "[Mock] " if epic.get("mock") else ""
            details: dict = {
                "epic_key": epic.get("key") or epic.get("id"),
                "epic_name": epic["title"],
                "mock": epic.get("mock", False),
            }
            issue_key = await get_linked_ticket_id(action_item_id)
            if issue_key and (epic.get("key") or epic.get("id")):
                link = await jira_mcp.link_issue_to_epic(issue_key, epic.get("key") or epic["id"])
                details["link"] = link
                if not link.get("linked") and link.get("error"):
                    details["link_note"] = "Epic found; automatic parent link failed — link in Jira UI if needed."

            await update_execution_log(
                log_id,
                OrchestrationStatus.SUCCESS,
                f'{mode_label}Linked issue to epic: "{epic["title"]}"'
                + (f" ({details.get('epic_key')})" if details.get("epic_key") else ""),
                details=details,
            )
        else:
            await update_execution_log(
                log_id,
                OrchestrationStatus.SUCCESS,
                f'No matching Jira epic for "{epic_name}". Issue left without epic link.',
                details={"searched_for": epic_name, "found": False},
            )

    except JiraMCPError as e:
        await update_execution_log(
            log_id,
            OrchestrationStatus.ERROR,
            f"Failed epic link: {str(e)}",
        )

    return await get_db().execution_logs.find_one({"_id": log["_id"]})


async def execute_update_documentation(
    action_item_id: str,
    meeting_id: str,
    meeting_title: str,
    description: str,
    doc_search_term: str | None = None,
    triggered_by: str = "user",
) -> dict:
    """Search Confluence for a page and append a comment."""
    log = await create_execution_log(
        ExecutionLogCreate(
            action_item_id=action_item_id,
            meeting_id=meeting_id,
            action=OrchestrationAction.UPDATE_CONFLUENCE,
            status=OrchestrationStatus.RUNNING,
            message=f"Searching Confluence: '{doc_search_term or 'docs'}'...",
            triggered_by=triggered_by,
        )
    )
    log_id = str(log["_id"])

    try:
        search_term = (doc_search_term or "").strip() or f"{meeting_title} {description}".strip()[:200]
        pages = await confluence_mcp.search_pages(search_term, limit=8)

        if pages:
            page = pages[0]
            body = f"Update from meeting «{meeting_title}»:\n\n{description}"
            comment_result = await confluence_mcp.add_page_comment(page["id"], body)

            mode_label = "[Mock] " if comment_result.get("mock") else ""
            await update_execution_log(
                log_id,
                OrchestrationStatus.SUCCESS,
                f'{mode_label}Comment added on Confluence page: "{page["title"][:50]}"',
                details={
                    "page_id": page["id"],
                    "page_title": page["title"],
                    "url": page.get("url"),
                    "action": "comment_added",
                    "mock": comment_result.get("mock", False),
                },
            )
        else:
            await update_execution_log(
                log_id,
                OrchestrationStatus.SKIPPED,
                f"No Confluence page matched '{search_term}'. Skipping doc update.",
                details={
                    "searched_for": search_term,
                    "suggestion": "Create a page or set CONFLUENCE_SPACE_KEY to narrow search",
                },
            )

    except ConfluenceMCPError as e:
        await update_execution_log(
            log_id,
            OrchestrationStatus.ERROR,
            f"Confluence error: {str(e)}",
        )

    return await get_db().execution_logs.find_one({"_id": log["_id"]})


async def execute_create_subtask(
    action_item_id: str,
    meeting_id: str,
    description: str,
    triggered_by: str = "user",
) -> dict:
    """Create a subtask."""
    log = await create_execution_log(
        ExecutionLogCreate(
            action_item_id=action_item_id,
            meeting_id=meeting_id,
            action=OrchestrationAction.CREATE_SUBTASK,
            status=OrchestrationStatus.RUNNING,
            message="Creating subtask...",
            triggered_by=triggered_by,
        )
    )
    log_id = str(log["_id"])

    try:
        result = await jira_mcp.create_ticket(
            title=f"[Subtask] {description[:80]}",
            description=description,
            ticket_type="task",
            priority="medium",
            status="To Do",
            source_meeting_id=meeting_id,
        )

        mode_label = "[Mock] " if result.get("mock") else ""
        key = result.get("key") or result["id"]
        await update_execution_log(
            log_id,
            OrchestrationStatus.SUCCESS,
            f'{mode_label}Created Jira sub-task issue: "{result["title"][:50]}..." ({key})',
            details={
                "ticket_id": key,
                "issue_key": key,
                "url": result["url"],
                "mock": result.get("mock", False),
            },
        )

    except JiraMCPError as e:
        await update_execution_log(
            log_id,
            OrchestrationStatus.ERROR,
            f"Failed to create subtask issue: {str(e)}",
        )

    return await get_db().execution_logs.find_one({"_id": log["_id"]})


async def execute_update_ticket_status(
    action_item_id: str,
    meeting_id: str,
    ticket_id: str,
    new_status: str,
    triggered_by: str = "user",
) -> dict:
    """Update Jira issue status (and summary transitions)."""
    log = await create_execution_log(
        ExecutionLogCreate(
            action_item_id=action_item_id,
            meeting_id=meeting_id,
            action=OrchestrationAction.UPDATE_TICKET_STATUS,
            status=OrchestrationStatus.RUNNING,
            message=f"Updating ticket status to '{new_status}'...",
            triggered_by=triggered_by,
        )
    )
    log_id = str(log["_id"])

    try:
        result = await jira_mcp.update_ticket(
            ticket_id=ticket_id,
            status=new_status,
        )

        mode_label = "[Mock] " if result.get("mock") else ""
        await update_execution_log(
            log_id,
            OrchestrationStatus.SUCCESS,
            f"{mode_label}Updated Jira issue to '{new_status}'",
            details={
                "ticket_id": ticket_id,
                "issue_key": ticket_id,
                "new_status": new_status,
                "url": result.get("url"),
                "mock": result.get("mock", False),
            },
        )

    except JiraMCPError as e:
        await update_execution_log(
            log_id,
            OrchestrationStatus.ERROR,
            f"Failed to update Jira issue: {str(e)}",
        )

    return await get_db().execution_logs.find_one({"_id": log["_id"]})


async def get_linked_ticket_id(action_item_id: str) -> str | None:
    """Issue key (e.g. SCRUM-42) from the latest successful create_jira_ticket log."""
    db = get_db()
    oid = _parse_oid(action_item_id, "Action item")

    cur = (
        db.execution_logs.find(
            {
                "action_item_id": oid,
                "action": OrchestrationAction.CREATE_JIRA_TICKET.value,
                "status": OrchestrationStatus.SUCCESS.value,
            }
        )
        .sort("created_at", -1)
        .limit(1)
    )
    logs = await cur.to_list(1)
    log = logs[0] if logs else None

    if log and log.get("details"):
        d = log["details"]
        return d.get("issue_key") or d.get("ticket_id")
    return None


async def execute_search_and_update_ticket(
    action_item_id: str,
    meeting_id: str,
    target_ticket_name: str | None,
    new_status: str = "Done",
    triggered_by: str = "user",
) -> dict:
    """
    Search for an existing ticket by name and update its status.
    This handles action items like "Update the story 'Ship metrics dashboard'".
    """
    log = await create_execution_log(
        ExecutionLogCreate(
            action_item_id=action_item_id,
            meeting_id=meeting_id,
            action=OrchestrationAction.UPDATE_TICKET_STATUS,
            status=OrchestrationStatus.RUNNING,
            message=f"Searching for ticket '{target_ticket_name}'...",
            triggered_by=triggered_by,
        )
    )
    log_id = str(log["_id"])

    if not target_ticket_name:
        await update_execution_log(
            log_id,
            OrchestrationStatus.ERROR,
            "Could not identify which ticket to update from the action item description",
        )
        return await get_db().execution_logs.find_one({"_id": log["_id"]})

    try:
        ticket = await jira_mcp.find_ticket_by_name(target_ticket_name)

        if not ticket:
            await update_execution_log(
                log_id,
                OrchestrationStatus.ERROR,
                f"No Jira issue found matching '{target_ticket_name}'",
                details={"searched_for": target_ticket_name},
            )
            return await get_db().execution_logs.find_one({"_id": log["_id"]})

        mode_label = "[Mock] " if ticket.get("mock") else ""
        tid = ticket.get("key") or ticket["id"]

        result = await jira_mcp.update_ticket(
            ticket_id=tid,
            status=new_status,
        )

        await update_execution_log(
            log_id,
            OrchestrationStatus.SUCCESS,
            f"{mode_label}Updated Jira '{ticket['title']}' ({tid}) → {new_status}",
            details={
                "ticket_id": tid,
                "issue_key": tid,
                "ticket_title": ticket["title"],
                "previous_status": ticket.get("status"),
                "new_status": new_status,
                "url": ticket.get("url") or result.get("url"),
                "mock": ticket.get("mock", False),
            },
        )

    except JiraMCPError as e:
        await update_execution_log(
            log_id,
            OrchestrationStatus.ERROR,
            f"Failed to update Jira issue: {str(e)}",
        )

    return await get_db().execution_logs.find_one({"_id": log["_id"]})


async def execute_update_meeting(
    meeting_id: str,
    title: str | None = None,
    notify_participants: bool = False,
    triggered_by: str = "user",
    action_item_id: str | None = None,
) -> dict:
    """Update meeting title and/or email participants (calendar uses execute_create_calendar_event)."""
    db = get_db()
    oid = _parse_oid(meeting_id, "Meeting")
    meeting = await db.meetings.find_one({"_id": oid})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    log_item_id = action_item_id.strip() if action_item_id else meeting_id

    log = await create_execution_log(
        ExecutionLogCreate(
            action_item_id=log_item_id,
            meeting_id=meeting_id,
            action=OrchestrationAction.UPDATE_MEETING,
            status=OrchestrationStatus.RUNNING,
            message="Updating meeting...",
            triggered_by=triggered_by,
        )
    )
    log_id = str(log["_id"])

    actions_taken: list[str] = []
    details: dict = {}

    if title:
        await db.meetings.update_one({"_id": oid}, {"$set": {"title": title}})
        actions_taken.append(f"Updated title to \"{title}\"")

    if notify_participants:
        emails = await list_meeting_attendee_emails(oid)
        deliverable, placeholder = partition_invite_recipients(emails)
        if not deliverable:
            if placeholder:
                actions_taken.append(
                    "Notify skipped: @example.com addresses are demo placeholders and are not emailed"
                )
            else:
                actions_taken.append("Notify skipped: no participant email addresses")
        elif not smtp_configured():
            actions_taken.append(
                "Email not configured: set SMTP_HOST and SMTP_FROM (and credentials) in .env"
            )
        else:
            title_mt = meeting.get("title", "Meeting")
            link_line = ""
            if settings.public_app_url:
                base = settings.public_app_url.rstrip("/")
                link_line = f"\nOpen in app: {base}/meetings/{meeting_id}\n"
            body = (
                f"This is an update regarding the meeting \"{title_mt}\".\n\n"
                f"Meeting ID: {meeting_id}\n"
                f"{link_line}\n"
                "— Sent from Meeting Intelligence"
            )
            try:
                await send_participant_digest(
                    to_addrs=deliverable,
                    meeting_title=title_mt,
                    body_text=body,
                )
                actions_taken.append(f"Sent email to {len(deliverable)} recipient(s)")
                details["email_recipient_count"] = len(deliverable)
            except Exception as e:
                actions_taken.append(f"Email failed: {e!s}")

    message = "; ".join(actions_taken) if actions_taken else "No changes made"

    details.update(
        {
            "title": title,
            "notify_participants": notify_participants,
        }
    )

    await update_execution_log(
        log_id,
        OrchestrationStatus.SUCCESS,
        message,
        details=details,
    )

    return await db.execution_logs.find_one({"_id": log["_id"]})


async def execute_create_calendar_event(
    action_item_id: str,
    meeting_id: str,
    title: str,
    description: str,
    calendar_time: str | None = None,
    source_snippet: str | None = None,
    attendees: list[str] | None = None,
    triggered_by: str = "user",
) -> dict:
    """Create a calendar event and send invites based on action item."""
    from zoneinfo import ZoneInfo

    from app.services.calendar_mcp import calendar_mcp, CalendarMCPError
    from dateparser import parse as parse_date

    tz_name = (settings.app_timezone or "UTC").strip() or "UTC"
    tz = ZoneInfo(tz_name)
    
    log = await create_execution_log(
        ExecutionLogCreate(
            action_item_id=action_item_id,
            meeting_id=meeting_id,
            action=OrchestrationAction.CREATE_CALENDAR_EVENT,
            status=OrchestrationStatus.RUNNING,
            message=f"Creating calendar event: {title}...",
            triggered_by=triggered_by,
        )
    )
    log_id = str(log["_id"])
    meeting_oid = _parse_oid(meeting_id, "Meeting")

    try:
        parse_settings = {
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": tz_name,
            "TO_TIMEZONE": tz_name,
            "RETURN_AS_TIMEZONE_AWARE": True,
        }
        parse_source: str | None = None
        if calendar_time and calendar_time.strip():
            parse_source = calendar_time.strip()
        else:
            blob = combined_schedule_text(description, source_snippet)
            if text_has_meeting_time_cue(blob):
                parse_source = blob

        if parse_source:
            event_time = parse_date(parse_source, settings=parse_settings)
        else:
            event_time = None

        if not event_time:
            now_local = datetime.now(timezone.utc).astimezone(tz)
            tomorrow_date = now_local.date() + timedelta(days=1)
            event_time = datetime.combine(tomorrow_date, time(10, 0), tzinfo=tz)
        elif event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=tz)
        else:
            event_time = event_time.astimezone(tz)

        pre_weekend = event_time
        event_time = move_weekend_to_monday(event_time)
        weekend_adjusted = event_time != pre_weekend

        end_time = event_time + timedelta(hours=1)

        if calendar_time and str(calendar_time).strip():
            time_resolution = "llm_calendar_time"
        elif parse_source:
            time_resolution = "parsed_action_item_text"
        else:
            time_resolution = "default_next_day_10am"

        # Get attendees from meeting roster (meeting_participants join), if not provided
        if not attendees:
            attendees = await list_meeting_attendee_emails(meeting_oid)
        attendee_list_full: list[str] = list(attendees) if attendees else []
        real_invitees, placeholder_invitees = partition_invite_recipients(attendee_list_full)
        roster_n = await count_meeting_participant_links(meeting_oid)

        event_description = (
            f"{description.rstrip()}\n\nCreated from Meeting Intelligence action item."
        )
        if placeholder_invitees:
            event_description += (
                "\n\n---\nPlaceholder roster emails (demo — not sent as calendar invites):\n"
                + "\n".join(f"- {e}" for e in placeholder_invitees)
            )

        cal_base: dict = {
            "kind": "calendar_invite",
            "event_title": title,
            "timezone": tz_name,
            "time_resolution": time_resolution,
            "time_resolution_label": {
                "llm_calendar_time": "From LLM / classifier calendar_time",
                "parsed_action_item_text": "Parsed from action + transcript (time cues found)",
                "default_next_day_10am": "Default — next day 10:00 (no time cues in text)",
            }.get(time_resolution, time_resolution),
            "parsed_from_preview": _parse_preview(parse_source) if parse_source else None,
            "weekend_adjusted": weekend_adjusted,
            "original_start_iso": pre_weekend.isoformat() if weekend_adjusted else None,
            "start_iso": event_time.isoformat(),
            "end_iso": end_time.isoformat(),
            "start_local_display": event_time.strftime("%a %Y-%m-%d %H:%M"),
            "end_local_display": end_time.strftime("%a %Y-%m-%d %H:%M"),
            "start_utc": event_time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "end_utc": event_time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "attendees_count": len(attendee_list_full),
            "attendee_emails": attendee_list_full[:40],
            "attendee_emails_truncated": len(attendee_list_full) > 40,
            "placeholder_emails_excluded_from_invite": placeholder_invitees[:40],
            "deliverable_attendee_emails": real_invitees[:40],
            "roster_participants_count": roster_n,
        }

        # Create the calendar event
        try:
            result = await calendar_mcp.create_event(
                title=title,
                start_time=event_time,
                end_time=end_time,
                description=event_description,
                attendees=real_invitees if real_invitees else None,
                meeting_id=meeting_id,
            )
        except CalendarMCPError as e:
            await update_execution_log(
                log_id,
                OrchestrationStatus.ERROR,
                f"Failed to create calendar event: {str(e)}",
                details={**cal_base, "stage": "google_calendar_api", "error": str(e)},
            )
            return await get_db().execution_logs.find_one({"_id": log["_id"]})

        mode_label = "[Mock] " if result.get("mock") else ""
        n_deliverable = len(real_invitees)
        n_full = len(attendee_list_full)
        invite_mode = result.get("invite_mode") or "none"

        if invite_mode == "description_only":
            invite_msg = (
                f"Event created — Google did not email invites (service account). "
                f"Roster email details are in the event description ({n_full} address(es), "
                f"{n_deliverable} deliverable). "
                "For real email invites on a personal Gmail, add OAuth env vars (see .env.example); "
                "Workspace accounts can use GOOGLE_WORKSPACE_DELEGATED_USER."
            )
        elif invite_mode == "sent" and n_deliverable:
            invite_msg = f"Sent {n_deliverable} calendar invite(s)"
        elif roster_n and n_deliverable == 0 and placeholder_invitees:
            invite_msg = (
                f"0 invites emailed — {len(placeholder_invitees)} address(es) are @example.com "
                "(demo); listed in event description. Use real emails for delivery."
            )
        elif roster_n and n_deliverable == 0:
            invite_msg = (
                f"0 invite(s) — roster lists {roster_n} people but none have emails on participant records"
            )
        elif n_deliverable:
            invite_msg = f"{n_deliverable} attendee(s) on event (no email sendUpdates)"
        else:
            invite_msg = "No attendees on roster emails"

        cal_details = {
            **cal_base,
            "event_id": result.get("id"),
            "calendar_link": result.get("html_link"),
            "invite_mode": invite_mode,
            "invite_summary": _calendar_invite_summary(invite_mode, n_deliverable),
            "planned_attendees": result.get("planned_attendees"),
            "mock": result.get("mock", False),
        }

        await update_execution_log(
            log_id,
            OrchestrationStatus.SUCCESS,
            f"{mode_label}Created calendar event: \"{title}\" — {invite_msg}"
            + (" — moved from weekend to Monday" if weekend_adjusted else ""),
            details=cal_details,
        )

    except Exception as e:
        await update_execution_log(
            log_id,
            OrchestrationStatus.ERROR,
            f"Calendar error: {str(e)}",
            details={"kind": "calendar_invite", "stage": "unexpected", "error": str(e)},
        )

    return await get_db().execution_logs.find_one({"_id": log["_id"]})


async def execute_auto_orchestration(
    action_item_id: str,
    meeting_id: str,
    description: str,
    priority: str,
    project_theme: str | None,
    meeting_title: str,
    source_snippet: str | None = None,
    transcript_context: str | None = None,
    other_action_items: list[str] | None = None,
    owner_name: str | None = None,
    due_date: str | None = None,
    triggered_by: str = "approval",
) -> list[dict]:
    """
    Execute full auto-orchestration workflow on approval.

    Uses LLM classifier to determine what actions to take.
    Passes full meeting context to the classifier for better extraction.
    """
    logs = []

    # Create parent log
    parent_log = await create_execution_log(
        ExecutionLogCreate(
            action_item_id=action_item_id,
            meeting_id=meeting_id,
            action=OrchestrationAction.AUTO_ORCHESTRATION,
            status=OrchestrationStatus.RUNNING,
            message="Classifying action item with full context...",
            triggered_by=triggered_by,
        )
    )
    parent_log_id = str(parent_log["_id"])

    try:
        # Step 1: Classify the action item using LLM with full context
        classification = await classify_action_item(
            description=description,
            source_snippet=source_snippet,
            project_theme=project_theme,
            meeting_title=meeting_title,
            existing_priority=priority,
            transcript_context=transcript_context,
            other_action_items=other_action_items,
            owner_name=owner_name,
            due_date=due_date,
        )

        # Update parent log with classification info
        await update_execution_log(
            parent_log_id,
            OrchestrationStatus.RUNNING,
            f"Classified as {classification.ticket_type.value} ({classification.confidence:.0%} confidence). Executing {len(classification.recommended_actions)} actions...",
            details={
                "classification": classification.to_dict(),
            },
        )

        actions_executed = 0

        # Check if LLM determined no action needed
        if not classification.recommended_actions or (
            len(classification.recommended_actions) == 1 
            and classification.recommended_actions[0] == ClassifierAction.NO_ACTION
        ):
            await update_execution_log(
                parent_log_id,
                OrchestrationStatus.SUCCESS,
                f"No automated action needed: {classification.reasoning}",
                details={
                    "classification": classification.to_dict(),
                    "actions_completed": 0,
                    "reason": classification.reasoning,
                },
            )
            logs.insert(0, await get_db().execution_logs.find_one({"_id": parent_log["_id"]}))
            return logs

        # Step 2: Execute recommended actions
        for action in classification.recommended_actions:
            if action == ClassifierAction.NO_ACTION:
                continue  # Skip no_action entries
                
            elif action == ClassifierAction.CREATE_TICKET:
                log = await execute_create_ticket(
                    action_item_id=action_item_id,
                    meeting_id=meeting_id,
                    description=description,
                    priority=classification.priority,
                    classification=classification,
                    source_snippet=source_snippet,
                    triggered_by=triggered_by,
                    meeting_title=meeting_title,
                    project_theme=project_theme,
                )
                logs.append(log)
                actions_executed += 1

            elif action == ClassifierAction.LINK_TO_EPIC:
                # Only link if we have an epic to link to
                epic_name = classification.suggested_epic or project_theme
                if epic_name:
                    log = await execute_link_to_epic(
                        action_item_id=action_item_id,
                        meeting_id=meeting_id,
                        project_theme=epic_name,
                        classification=classification,
                        triggered_by=triggered_by,
                    )
                    logs.append(log)
                    actions_executed += 1

            elif action == ClassifierAction.UPDATE_DOCUMENTATION:
                log = await execute_update_documentation(
                    action_item_id=action_item_id,
                    meeting_id=meeting_id,
                    meeting_title=meeting_title,
                    description=description,
                    doc_search_term=classification.doc_search_term,
                    triggered_by=triggered_by,
                )
                logs.append(log)
                actions_executed += 1

            elif action == ClassifierAction.CREATE_SUBTASK:
                log = await execute_create_subtask(
                    action_item_id=action_item_id,
                    meeting_id=meeting_id,
                    description=description,
                    triggered_by=triggered_by,
                )
                logs.append(log)
                actions_executed += 1

            elif action == ClassifierAction.UPDATE_TICKET:
                # Search for and update existing ticket
                log = await execute_search_and_update_ticket(
                    action_item_id=action_item_id,
                    meeting_id=meeting_id,
                    target_ticket_name=classification.target_ticket_name,
                    new_status=classification.new_status or "Done",
                    triggered_by=triggered_by,
                )
                logs.append(log)
                actions_executed += 1

            elif action == ClassifierAction.CREATE_CALENDAR_EVENT:
                # Create calendar event and send invites
                event_title = classification.extracted_title or description[:50]
                log = await execute_create_calendar_event(
                    action_item_id=action_item_id,
                    meeting_id=meeting_id,
                    title=event_title,
                    description=description,
                    calendar_time=classification.calendar_time,
                    source_snippet=source_snippet,
                    triggered_by=triggered_by,
                )
                logs.append(log)
                actions_executed += 1
            
            elif action == ClassifierAction.SCHEDULE_MEETING:
                # Also handle schedule_meeting as calendar event
                event_title = classification.extracted_title or description[:50]
                log = await execute_create_calendar_event(
                    action_item_id=action_item_id,
                    meeting_id=meeting_id,
                    title=event_title,
                    description=description,
                    calendar_time=classification.calendar_time,
                    source_snippet=source_snippet,
                    triggered_by=triggered_by,
                )
                logs.append(log)
                actions_executed += 1

        # Update parent log with completion
        summary = f"Completed {actions_executed} action(s)"
        if classification.reasoning:
            summary += f" - {classification.reasoning}"
            
        await update_execution_log(
            parent_log_id,
            OrchestrationStatus.SUCCESS,
            summary,
            details={
                "classification": classification.to_dict(),
                "actions_completed": actions_executed,
            },
        )
        logs.insert(0, await get_db().execution_logs.find_one({"_id": parent_log["_id"]}))

    except Exception as e:
        await update_execution_log(
            parent_log_id,
            OrchestrationStatus.ERROR,
            f"Auto-orchestration failed: {str(e)}",
        )
        logs.insert(0, await get_db().execution_logs.find_one({"_id": parent_log["_id"]}))

    return logs


def execution_log_to_out(doc: dict) -> dict:
    """Convert execution log document to output format."""
    return {
        "id": str(doc["_id"]),
        "action_item_id": str(doc["action_item_id"]),
        "meeting_id": str(doc["meeting_id"]),
        "action": doc["action"],
        "status": doc["status"],
        "message": doc["message"],
        "details": doc.get("details"),
        "triggered_by": doc["triggered_by"],
        "created_at": doc["created_at"],
        "updated_at": doc.get("updated_at"),
    }
