from pydantic import BaseModel, Field


class ParticipantBase(BaseModel):
    display_name: str
    email: str | None = None


class ParticipantOut(BaseModel):
    id: str
    display_name: str
    email: str | None = None


class MeetingParticipantOut(BaseModel):
    participant: ParticipantOut
    role: str | None = None


class MeetingTeamMemberCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    add_to_linked_project: bool = Field(
        default=True,
        description="When the meeting has a linked project_id, also add this person to the project roster.",
    )
