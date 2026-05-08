from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class OrchestrationAction(str, Enum):
    CREATE_JIRA_TICKET = "create_jira_ticket"  # Creates Notion ticket
    LINK_TO_EPIC = "link_to_epic"
    UPDATE_CONFLUENCE = "update_confluence"  # Update documentation
    CREATE_SUBTASK = "create_subtask"
    UPDATE_MEETING = "update_meeting"
    PUSH_TO_CALENDAR = "push_to_calendar"
    CREATE_CALENDAR_EVENT = "create_calendar_event"  # Create calendar invite from action item
    NOTIFY_TEAM = "notify_team"
    AUTO_ORCHESTRATION = "auto_orchestration"
    UPDATE_TICKET_STATUS = "update_ticket_status"  # Update existing ticket


class OrchestrationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


class ExecutionLogCreate(BaseModel):
    action_item_id: str
    meeting_id: str
    action: OrchestrationAction
    status: OrchestrationStatus = OrchestrationStatus.PENDING
    message: str = ""
    details: dict | None = None
    triggered_by: str = "system"


class ExecutionLogOut(BaseModel):
    id: str
    action_item_id: str
    meeting_id: str
    action: OrchestrationAction
    status: OrchestrationStatus
    message: str
    details: dict | None = None
    triggered_by: str
    created_at: datetime
    updated_at: datetime | None = None


class ExecutionLogsPageOut(BaseModel):
    items: list[ExecutionLogOut]
    total: int


class OrchestrationTriggerRequest(BaseModel):
    action: OrchestrationAction | None = None
    # For UPDATE_TICKET_STATUS action
    new_status: str | None = None  # "In Progress", "Done", etc.
    ticket_id: str | None = None  # Notion ticket ID to update


class OrchestrationTriggerResponse(BaseModel):
    triggered: bool
    execution_log_id: str | None = None
    message: str


class MeetingUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    push_to_calendar: bool = False
    notify_participants: bool = False
    action_item_id: str | None = None
