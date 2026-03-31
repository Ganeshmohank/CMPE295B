from fastapi import APIRouter, Query

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
) -> ProcessingLogsPageOut:
    docs, total = await processing_logs_page(
        page=page, page_size=page_size, stage=stage, status=status
    )
    return ProcessingLogsPageOut(
        items=[ProcessingLogOut(**processing_log_to_out(d)) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )
