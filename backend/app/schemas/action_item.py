from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import ActionItemStatus, Priority
from app.schemas.participant import MeetingParticipantOut
from app.schemas.processing_log import ProcessingLogOut


class ActionItemBase(BaseModel):
    description: str
    owner_name: str | None = None
    due_date: date | None = None
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
    status: ActionItemStatus
    source_snippet: str | None = None


class ActionItemCreate(ActionItemBase):
    meeting_id: str


class ActionItemUpdate(BaseModel):
    description: str | None = None
    owner_name: str | None = None
    due_date: date | None = None
    priority: Priority | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: ActionItemStatus | None = None
    source_snippet: str | None = None

    @field_validator("due_date")
    @classmethod
    def due_date_range(cls, v: date | None) -> date | None:
        if v is None:
            return v
        if v.year < 2020 or v.year > 2035:
            raise ValueError("due_date must be between 2020 and 2035")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> ActionItemUpdate:
        data = self.model_dump(exclude_unset=True)
        if not data:
            raise ValueError("At least one field must be provided for update")
        return self


class ActionItemOut(ActionItemBase):
    id: str
    meeting_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ActionItemReviewOut(ActionItemOut):
    meeting_title: str
    meeting_start_time: datetime


class ReviewQueuePageOut(BaseModel):
    items: list[ActionItemReviewOut]
    page: int
    page_size: int
    total_meetings: int
    total_pending_items: int


class ActionItemReviewDetailOut(ActionItemReviewOut):
    """Review item plus meeting participants and pipeline logs (same shapes as meeting detail)."""

    participants: list[MeetingParticipantOut]
    processing_logs: list[ProcessingLogOut]


class ActionItemApproveBody(BaseModel):
    pass


class ActionItemRejectBody(BaseModel):
    reason: str | None = None
