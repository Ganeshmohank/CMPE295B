from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    speaker: str | None = None
    text: str


class TranscriptBase(BaseModel):
    meeting_id: str
    raw_text: str
    segments: list[TranscriptSegment] | None = None
    transcript_length: int = Field(ge=0)
    created_at: datetime


class TranscriptCreate(BaseModel):
    meeting_id: str
    raw_text: str
    segments: list[dict[str, Any]] | None = None
    transcript_length: int | None = None
    created_at: datetime | None = None


class TranscriptOut(BaseModel):
    id: str
    meeting_id: str
    raw_text: str
    segments: list[TranscriptSegment] | None = None
    transcript_length: int
    created_at: datetime


class TranscriptUpdate(BaseModel):
    raw_text: str | None = None
