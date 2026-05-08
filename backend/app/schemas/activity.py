from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.orchestration import OrchestrationAction, OrchestrationStatus


class ActivityLogOut(BaseModel):
    id: str
    action_item_id: str
    meeting_id: str
    meeting_title: str = ""
    action_item_preview: str = ""
    action: OrchestrationAction
    status: OrchestrationStatus
    message: str
    details: dict | None = None
    triggered_by: str
    created_at: datetime
    updated_at: datetime | None = None


class ActivityPageOut(BaseModel):
    items: list[ActivityLogOut]
    total: int
    page: int
    page_size: int
