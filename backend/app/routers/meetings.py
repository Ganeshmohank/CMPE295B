from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Header, HTTPException

from app.config import settings

from app.db import get_db
from app.schemas.detail import MeetingDetailResponse
from app.schemas.related_link import RelatedLinkOut
from app.schemas.meeting import (
    MeetingArchiveBody,
    MeetingContextPatch,
    MeetingMetadata,
    MeetingNotionRecapRequest,
    MeetingNotionRecapResponse,
    ReExtractActionsResponse,
)
from app.schemas.common import parse_oid
from app.schemas.participant import MeetingParticipantOut, MeetingTeamMemberCreate
from app.schemas.transcript import TranscriptOut, TranscriptUpdate
from app.serializers import (
    action_item_to_out,
    meeting_to_metadata,
    processing_log_to_out,
    transcript_to_out,
)
from app.services.meeting_context import merge_meeting_display_context
from app.services.meetings import get_meeting_or_none, load_meeting_detail
from app.services.related_links import effective_related_links
from app.services.meeting_notion_recap import post_meeting_notion_recap, verify_internal_secret
from app.services.team_roster import add_meeting_team_member
from app.services.transcript_extraction import re_extract_action_items_for_meeting

router = APIRouter()


@router.patch("/{meeting_id}/context", response_model=MeetingMetadata)
async def patch_meeting_context(
    meeting_id: str, body: MeetingContextPatch
) -> MeetingMetadata:
    try:
        oid = parse_oid(meeting_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Meeting not found") from e
    m = await get_meeting_or_none(meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    data = body.model_dump(exclude_unset=True)
    explicit_keys = set(data.keys())

    if "project_id" in data:
        raw = data.pop("project_id")
        if raw is None:
            updates["project_id"] = None
        else:
            try:
                poid = ObjectId(raw)
            except InvalidId as e:
                raise HTTPException(status_code=422, detail="Invalid project_id") from e
            proj = await get_db().projects.find_one({"_id": poid})
            if not proj:
                raise HTTPException(status_code=404, detail="Project not found")
            updates["project_id"] = poid
            if "project_theme" not in data:
                updates["project_theme"] = proj["name"]

    for k, v in data.items():
        updates[k] = v

    # Related docs live on `projects.related_links`. Drop any stale per-meeting copy when project link changes.
    update_op: dict = {"$set": updates}
    if "project_id" in explicit_keys:
        update_op["$unset"] = {"related_links": ""}

    await get_db().meetings.update_one({"_id": oid}, update_op)
    fresh = await get_meeting_or_none(meeting_id)
    assert fresh is not None
    merged = await merge_meeting_display_context(fresh)
    return MeetingMetadata(**meeting_to_metadata(fresh, merged_context=merged))


@router.patch("/{meeting_id}/archive", response_model=MeetingMetadata)
async def patch_meeting_archive(meeting_id: str, body: MeetingArchiveBody) -> MeetingMetadata:
    """Hide or restore a meeting on main lists (data retained)."""
    try:
        oid = parse_oid(meeting_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Meeting not found") from e
    m = await get_meeting_or_none(meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    await get_db().meetings.update_one(
        {"_id": oid},
        {"$set": {"archived": body.archived, "updated_at": datetime.now(timezone.utc)}},
    )
    fresh = await get_meeting_or_none(meeting_id)
    assert fresh is not None
    merged = await merge_meeting_display_context(fresh)
    return MeetingMetadata(**meeting_to_metadata(fresh, merged_context=merged))


@router.post("/{meeting_id}/re-extract-actions", response_model=ReExtractActionsResponse)
async def post_re_extract_actions(meeting_id: str) -> ReExtractActionsResponse:
    """Re-run LLM extraction from the saved transcript (replaces existing action items)."""
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")
    try:
        out = await re_extract_action_items_for_meeting(meeting_id.strip())
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from e
        if msg.startswith("OpenAI request failed"):
            raise HTTPException(status_code=502, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    return ReExtractActionsResponse(**out)


@router.post(
    "/{meeting_id}/team-members",
    response_model=MeetingParticipantOut,
)
async def post_meeting_team_member(
    meeting_id: str, body: MeetingTeamMemberCreate
) -> MeetingParticipantOut:
    """Add a person to this meeting (and, by default, to the meeting's linked project roster)."""
    try:
        parse_oid(meeting_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Meeting not found") from e
    return await add_meeting_team_member(
        meeting_id,
        body.display_name,
        body.email,
        body.add_to_linked_project,
    )


@router.patch("/{meeting_id}/transcript", response_model=TranscriptOut)
async def patch_transcript(meeting_id: str, body: TranscriptUpdate) -> TranscriptOut:
    try:
        oid = parse_oid(meeting_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Meeting not found") from e
    m = await get_meeting_or_none(meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    transcript = await get_db().transcripts.find_one({"meeting_id": oid})
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.raw_text is not None:
        updates["raw_text"] = body.raw_text
        updates["transcript_length"] = len(body.raw_text)
    await get_db().transcripts.update_one({"_id": transcript["_id"]}, {"$set": updates})
    fresh = await get_db().transcripts.find_one({"_id": transcript["_id"]})
    assert fresh is not None
    return TranscriptOut(**transcript_to_out(fresh))


@router.post(
    "/{meeting_id}/notion-recap",
    response_model=MeetingNotionRecapResponse,
)
async def post_notion_meeting_recap(
    meeting_id: str,
    body: MeetingNotionRecapRequest | None = None,
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> MeetingNotionRecapResponse:
    """
    Create a Notion child page with meeting narrative + action items.
    Intended to be called by station-alpha after transcript extraction; can also be triggered manually.
    """
    verify_internal_secret(x_internal_secret)
    force = body.force if body else False
    result = await post_meeting_notion_recap(meeting_id.strip(), force=force)
    return MeetingNotionRecapResponse(**result)


@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
async def meeting_detail(meeting_id: str) -> MeetingDetailResponse:
    detail = await load_meeting_detail(meeting_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Meeting not found")
    m = detail["meeting"]
    transcript = detail["transcript"]
    merged = await merge_meeting_display_context(m)
    proj = None
    pid = m.get("project_id")
    if isinstance(pid, ObjectId):
        proj = await get_db().projects.find_one({"_id": pid})
    raw_links = effective_related_links(m, proj)
    related_out = [RelatedLinkOut(title=x["title"], url=x["url"]) for x in raw_links]
    return MeetingDetailResponse(
        meeting=MeetingMetadata(**meeting_to_metadata(m, merged_context=merged)),
        transcript=transcript_to_out(transcript) if transcript else None,
        participants=detail["participants"],
        action_items=[action_item_to_out(a) for a in detail["action_items"]],
        processing_logs=[processing_log_to_out(l) for l in detail["processing_logs"]],
        related_links=related_out,
    )


@router.get("/{meeting_id}/meta", response_model=MeetingMetadata)
async def meeting_meta(meeting_id: str) -> MeetingMetadata:
    m = await get_meeting_or_none(meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    merged = await merge_meeting_display_context(m)
    return MeetingMetadata(**meeting_to_metadata(m, merged_context=merged))
