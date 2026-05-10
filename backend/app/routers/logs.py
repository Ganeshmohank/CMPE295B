from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query

from app.domain.enums import LogStage, LogStatus
from app.schemas.processing_log import ProcessingLogOut, ProcessingLogsPageOut
from app.serializers import processing_log_to_out
from app.services.observability import processing_logs_page

router = APIRouter()


@router.get("/processing", response_model=ProcessingLogsPageOut)
async def processing_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=10),
    stage: LogStage | None = None,
    status: LogStatus | None = None,
    meeting_id: str | None = Query(
        None,
        description="Only logs for this meeting id (Mongo ObjectId hex string)",
    ),
    q: str | None = Query(None, description="Message contains (case-insensitive)"),
) -> ProcessingLogsPageOut:
    oid: ObjectId | None = None
    if meeting_id is not None and meeting_id.strip():
        try:
            oid = ObjectId(meeting_id.strip())
        except InvalidId as e:
            raise HTTPException(status_code=400, detail="Invalid meeting_id") from e

    docs, total = await processing_logs_page(
        page=page,
        page_size=page_size,
        stage=stage,
        status=status,
        meeting_id=oid,
        message_contains=q,
    )
    return ProcessingLogsPageOut(
        items=[ProcessingLogOut(**processing_log_to_out(d)) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )
