from pydantic import BaseModel, Field

from app.schemas.action_item import ActionItemOut
from app.schemas.meeting import MeetingMetadata
from app.schemas.participant import MeetingParticipantOut
from app.schemas.processing_log import ProcessingLogOut
from app.schemas.related_link import RelatedLinkOut
from app.schemas.transcript import TranscriptOut


class MeetingDetailResponse(BaseModel):
    meeting: MeetingMetadata
    transcript: TranscriptOut | None
    participants: list[MeetingParticipantOut]
    action_items: list[ActionItemOut]
    processing_logs: list[ProcessingLogOut]
    related_links: list[RelatedLinkOut] = Field(default_factory=list)
