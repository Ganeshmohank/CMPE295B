from fastapi import APIRouter, Query

from app.schemas.activity import ActivityLogOut, ActivityPageOut
from app.services import activity as activity_service

router = APIRouter()


@router.get("", response_model=ActivityPageOut)
async def list_activity(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
) -> ActivityPageOut:
    """All orchestration / automation execution logs (user and system triggered)."""
    docs, total = await activity_service.activity_feed(page=page, page_size=page_size)
    return ActivityPageOut(
        items=[ActivityLogOut(**d) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )
