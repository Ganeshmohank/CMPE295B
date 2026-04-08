from fastapi import APIRouter, HTTPException

from app.db import get_db
from app.schemas.common import parse_oid
from app.schemas.participant import MeetingParticipantOut
from app.schemas.project import ProjectListItem, ProjectOut
from app.schemas.related_link import RelatedLinkOut
from app.services.related_links import normalize_link_dicts
from app.services.team_roster import list_project_team_member_rows

router = APIRouter()


async def _list_projects() -> list[ProjectListItem]:
    """Rows from `projects`, plus any `meetings.project_theme` not yet in that catalog.

    If the DB was populated without the projects collection (or it was cleared), meetings still
    carry initiative labels — those appear with empty `id` until a matching `projects` doc exists.
    """
    db = get_db()
    seen: set[str] = set()
    out: list[ProjectListItem] = []

    async for doc in db.projects.find().sort("name", 1):
        name = doc.get("name")
        if not name or not isinstance(name, str):
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(ProjectListItem(id=str(doc["_id"]), name=name.strip()))

    for raw in await db.meetings.distinct("project_theme"):
        if raw is None:
            continue
        name = str(raw).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(ProjectListItem(id="", name=name))

    out.sort(key=lambda p: p.name.casefold())
    return out


# Explicit path first (before /{project_id}) — avoids empty-route / proxy quirks; also used by the UI.
@router.get("/catalog", response_model=list[ProjectListItem])
@router.get("", response_model=list[ProjectListItem])
@router.get("/", response_model=list[ProjectListItem])
async def list_projects() -> list[ProjectListItem]:
    """Catalog initiatives for linking meetings and autocomplete."""
    return await _list_projects()


@router.get("/{project_id}/team-members", response_model=list[MeetingParticipantOut])
async def list_project_team_members(project_id: str) -> list[MeetingParticipantOut]:
    """People on the initiative roster (may differ from who attended this meeting)."""
    try:
        oid = parse_oid(project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Project not found") from e
    rows = await list_project_team_member_rows(oid)
    return [MeetingParticipantOut(**r) for r in rows]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str) -> ProjectOut:
    try:
        oid = parse_oid(project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Project not found") from e
    doc = await get_db().projects.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    links = [RelatedLinkOut(title=x["title"], url=x["url"]) for x in normalize_link_dicts(doc.get("related_links"))]
    return ProjectOut(
        id=str(doc["_id"]),
        name=doc["name"],
        context_developer=doc.get("context_developer"),
        context_pm=doc.get("context_pm"),
        related_links=links,
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )
