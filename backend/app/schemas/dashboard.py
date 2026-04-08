from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.meeting import MeetingListItem


class DashboardSummary(BaseModel):
    total_meetings: int
    total_processed_meetings: int
    total_transcripts: int
    total_action_items: int
    total_pending_reviews: int
    total_failed_pipelines: int
    average_processing_time_ms: float | None = Field(
        description="Average of completed log entries with processing_time_ms"
    )
    success_rate: float | None = Field(
        description="Share of meetings with processing_status=processed among terminal outcomes"
    )
    window_days: Literal[7, 30] = 7
    meetings_in_window: int = 0
    action_items_in_window: int = 0
    pipelines_in_progress: int = 0
    pipelines_not_started: int = 0
    total_participant_seats: int = Field(
        default=0, description="Sum of participants_count across all meetings"
    )
    avg_action_items_per_meeting: float | None = None
    avg_transcript_length: float | None = None
    pending_review_avg_confidence: float | None = None
    pending_review_low_confidence: int = Field(
        default=0, description="Pending review items with confidence < 0.65"
    )
    action_items_approved_or_ticketed: int = 0
    action_items_rejected: int = 0
    action_items_ticket_created: int = 0
    human_review_throughput_rate: float | None = Field(
        default=None,
        description="(approved+ticket_created) / (approved+ticket_created+rejected), excluding pending_review",
    )
    meetings_by_processing_status: dict[str, int] = Field(default_factory=dict)
    meetings_by_meeting_status: dict[str, int] = Field(default_factory=dict)
    action_items_by_status: dict[str, int] = Field(default_factory=dict)


class MeetingsListSummary(BaseModel):
    """Global counts for KPI row (not affected by list filters)."""

    all_meetings: int
    all_action_items: int
    all_pending_review: int
    all_participant_seats: int


class MeetingsListPageOut(BaseModel):
    items: list[MeetingListItem]
    total: int = Field(description="Meetings matching current filters")
    page: int
    page_size: int
    summary: MeetingsListSummary
