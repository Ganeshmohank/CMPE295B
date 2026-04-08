from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.related_link import RelatedLinkOut


class ProjectListItem(BaseModel):
    id: str
    name: str


class ProjectOut(BaseModel):
    id: str
    name: str
    context_developer: str | None = None
    context_pm: str | None = None
    related_links: list[RelatedLinkOut] = Field(
        default_factory=list,
        description="Canonical external docs (Jira/Confluence, etc.); meetings inherit unless overridden.",
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None
