from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import LogStage, LogStatus


class ProcessingLogBase(BaseModel):
    meeting_id: str
    stage: LogStage
    status: LogStatus
    message: str
    processing_time_ms: int | None = Field(default=None, ge=0)
    timestamp: datetime


class ProcessingLogCreate(ProcessingLogBase):
    pass


class ProcessingLogOut(ProcessingLogBase):
    id: str


class ProcessingLogsPageOut(BaseModel):
    items: list[ProcessingLogOut]
    total: int
    page: int
    page_size: int
