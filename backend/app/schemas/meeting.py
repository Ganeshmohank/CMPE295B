from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import MeetingStatus, ProcessingStatus


class NotionRecapOut(BaseModel):
    page_id: str | None = None
    url: str | None = None
    posted_at: datetime | None = None


class MeetingBase(BaseModel):
    title: str
    source: str = "zoom"
    start_time: datetime
    duration_minutes: int = Field(ge=0)
    status: MeetingStatus
    processing_status: ProcessingStatus
    participants_count: int = Field(ge=0, default=0)


class MeetingCreate(MeetingBase):
    pass


class MeetingUpdate(BaseModel):
    title: str | None = None
    source: str | None = None
    start_time: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    status: MeetingStatus | None = None
    processing_status: ProcessingStatus | None = None
    participants_count: int | None = Field(default=None, ge=0)


class MeetingListItem(BaseModel):
    id: str
    title: str
    source: str = "zoom"
    date: datetime
    duration_minutes: int = 0
    status: MeetingStatus
    processing_status: ProcessingStatus
    participants_count: int
    action_items_count: int = 0
    pending_review_count: int = 0
    transcript_length: int | None = None
    archived: bool = False


class MeetingMetadata(BaseModel):
    id: str
    title: str
    source: str
    start_time: datetime
    duration_minutes: int
    status: MeetingStatus
    processing_status: ProcessingStatus
    participants_count: int
    archived: bool = False
    project_id: str | None = Field(default=None, description="Linked projects._id when normalized")
    project_theme: str | None = Field(default=None)
    context_developer: str | None = Field(default=None)
    context_pm: str | None = Field(default=None)
    notion_recap: NotionRecapOut | None = Field(
        default=None, description="Notion page created for meeting recap when posted"
    )


class MeetingArchiveBody(BaseModel):
    archived: bool


class ReExtractActionsResponse(BaseModel):
    extracted_count: int
    processing_time_ms: int


class MeetingContextPatch(BaseModel):
    """Set project_id to attach a catalog project; optional fields override project template when set."""

    project_id: str | None = None
    project_theme: str | None = None
    context_developer: str | None = None
    context_pm: str | None = None


class ProjectThemesOut(BaseModel):
    themes: list[str]


class MeetingNotionRecapRequest(BaseModel):
    force: bool = False


class MeetingNotionRecapResponse(BaseModel):
    posted: bool
    skipped_reason: str | None = None
    notion_url: str | None = None
    page_id: str | None = None
    mock: bool | None = None
