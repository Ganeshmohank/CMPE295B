from fastapi import APIRouter, HTTPException

from bson import ObjectId
from bson.errors import InvalidId

from app.db import get_db
from app.schemas.orchestration import (
    ExecutionLogOut,
    ExecutionLogsPageOut,
    MeetingUpdateRequest,
    OrchestrationAction,
    OrchestrationTriggerRequest,
    OrchestrationTriggerResponse,
)
from app.services import orchestration as orchestration_service
from app.services.action_items import get_action_item_or_404

router = APIRouter()


@router.get("/action-items/{item_id}/logs", response_model=ExecutionLogsPageOut)
async def get_action_item_execution_logs(item_id: str) -> ExecutionLogsPageOut:
    """Get all execution logs for an action item."""
    await get_action_item_or_404(item_id)
    logs = await orchestration_service.get_execution_logs_for_action_item(item_id)
    return ExecutionLogsPageOut(
        items=[ExecutionLogOut(**orchestration_service.execution_log_to_out(l)) for l in logs],
        total=len(logs),
    )


@router.get("/meetings/{meeting_id}/logs", response_model=ExecutionLogsPageOut)
async def get_meeting_execution_logs(meeting_id: str) -> ExecutionLogsPageOut:
    """Get all execution logs for a meeting."""
    logs = await orchestration_service.get_execution_logs_for_meeting(meeting_id)
    return ExecutionLogsPageOut(
        items=[ExecutionLogOut(**orchestration_service.execution_log_to_out(l)) for l in logs],
        total=len(logs),
    )


@router.post("/action-items/{item_id}/trigger", response_model=OrchestrationTriggerResponse)
async def trigger_orchestration(
    item_id: str,
    body: OrchestrationTriggerRequest,
) -> OrchestrationTriggerResponse:
    """Trigger a specific orchestration action or re-trigger full orchestration."""
    doc = await get_action_item_or_404(item_id)
    meeting_id = str(doc["meeting_id"])
    meeting = await get_db().meetings.find_one({"_id": doc["meeting_id"]})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if body.action is None:
        tctx, other, owner_name, due_s = await orchestration_service.build_classification_context(
            doc["meeting_id"],
            doc["_id"],
            doc,
        )
        logs = await orchestration_service.execute_auto_orchestration(
            action_item_id=item_id,
            meeting_id=meeting_id,
            description=doc["description"],
            priority=doc["priority"],
            project_theme=meeting.get("project_theme"),
            meeting_title=meeting["title"],
            source_snippet=doc.get("source_snippet"),
            transcript_context=tctx,
            other_action_items=other,
            owner_name=owner_name,
            due_date=due_s,
            triggered_by="manual_retrigger",
        )
        return OrchestrationTriggerResponse(
            triggered=True,
            execution_log_id=str(logs[0]["_id"]) if logs else None,
            message=f"Re-triggered full orchestration ({len(logs)} actions)",
        )

    if body.action == OrchestrationAction.CREATE_JIRA_TICKET:
        log = await orchestration_service.execute_create_ticket(
            action_item_id=item_id,
            meeting_id=meeting_id,
            description=doc["description"],
            priority=doc["priority"],
            source_snippet=doc.get("source_snippet"),
            triggered_by="manual",
            meeting_title=meeting["title"],
            project_theme=meeting.get("project_theme"),
        )
    elif body.action == OrchestrationAction.LINK_TO_EPIC:
        log = await orchestration_service.execute_link_to_epic(
            action_item_id=item_id,
            meeting_id=meeting_id,
            project_theme=meeting.get("project_theme"),
            triggered_by="manual",
        )
    elif body.action == OrchestrationAction.UPDATE_CONFLUENCE:
        log = await orchestration_service.execute_update_documentation(
            action_item_id=item_id,
            meeting_id=meeting_id,
            meeting_title=meeting["title"],
            description=doc["description"],
            triggered_by="manual",
        )
    elif body.action == OrchestrationAction.CREATE_SUBTASK:
        log = await orchestration_service.execute_create_subtask(
            action_item_id=item_id,
            meeting_id=meeting_id,
            description=doc["description"],
            triggered_by="manual",
        )
    elif body.action == OrchestrationAction.UPDATE_TICKET_STATUS:
        # Find the linked ticket if not provided
        ticket_id = body.ticket_id
        if not ticket_id:
            ticket_id = await orchestration_service.get_linked_ticket_id(item_id)
        if not ticket_id:
            raise HTTPException(status_code=400, detail="No linked Jira issue found for this action item")
        if not body.new_status:
            raise HTTPException(status_code=400, detail="new_status is required")
        
        log = await orchestration_service.execute_update_ticket_status(
            action_item_id=item_id,
            meeting_id=meeting_id,
            ticket_id=ticket_id,
            new_status=body.new_status,
            triggered_by="manual",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

    return OrchestrationTriggerResponse(
        triggered=True,
        execution_log_id=str(log["_id"]),
        message=log["message"],
    )


@router.post("/meetings/{meeting_id}/update", response_model=OrchestrationTriggerResponse)
async def trigger_meeting_update(
    meeting_id: str,
    body: MeetingUpdateRequest,
) -> OrchestrationTriggerResponse:
    """Title/notify via execute_update_meeting; Push to Calendar uses execute_create_calendar_event."""
    try:
        meeting_oid = ObjectId(meeting_id)
    except InvalidId as e:
        raise HTTPException(status_code=404, detail="Meeting not found") from e

    messages: list[str] = []
    last_log_id: str | None = None

    has_meta = bool(body.title and body.title.strip()) or body.notify_participants
    if has_meta:
        log = await orchestration_service.execute_update_meeting(
            meeting_id=meeting_id,
            title=body.title,
            notify_participants=body.notify_participants,
            triggered_by="manual",
            action_item_id=body.action_item_id,
        )
        messages.append(log["message"])
        last_log_id = str(log["_id"])

    if body.push_to_calendar:
        if not body.action_item_id or not body.action_item_id.strip():
            raise HTTPException(
                status_code=400,
                detail="action_item_id is required for Push to Calendar",
            )
        doc = await get_action_item_or_404(body.action_item_id.strip())
        if doc["meeting_id"] != meeting_oid:
            raise HTTPException(
                status_code=400,
                detail="Action item does not belong to this meeting",
            )
        meeting = await get_db().meetings.find_one({"_id": meeting_oid})
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        title = orchestration_service.derive_calendar_event_title(doc, meeting)
        log = await orchestration_service.execute_create_calendar_event(
            action_item_id=body.action_item_id.strip(),
            meeting_id=meeting_id,
            title=title,
            description=doc["description"],
            calendar_time=None,
            source_snippet=doc.get("source_snippet"),
            triggered_by="manual",
        )
        messages.append(log["message"])
        last_log_id = str(log["_id"])

    if not has_meta and not body.push_to_calendar:
        raise HTTPException(status_code=400, detail="No action requested")

    return OrchestrationTriggerResponse(
        triggered=True,
        execution_log_id=last_log_id,
        message="; ".join(messages),
    )
