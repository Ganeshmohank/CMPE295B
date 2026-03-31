from datetime import datetime

from pydantic import BaseModel, Field


class ProjectListItem(BaseModel):
    id: str
    name: str


class ProjectOut(BaseModel):
    id: str
    name: str
    context_developer: str | None = None
    context_pm: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
