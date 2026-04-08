from pydantic import BaseModel, Field


class RelatedLinkOut(BaseModel):
    title: str = Field(min_length=1)
    url: str = Field(min_length=1, description="External URL (e.g. Confluence, Jira)")
