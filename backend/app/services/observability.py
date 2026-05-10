import re

from bson import ObjectId

from app.db import get_db
from app.domain.enums import LogStage, LogStatus


async def recent_processing_logs(
    limit: int = 100,
    stage: LogStage | None = None,
    status: LogStatus | None = None,
) -> list[dict]:
    q: dict = {}
    if stage is not None:
        q["stage"] = stage.value
    if status is not None:
        q["status"] = status.value
    cursor = (
        get_db()
        .processing_logs.find(q)
        .sort("timestamp", -1)
        .limit(min(max(limit, 1), 500))
    )
    return await cursor.to_list(None)


async def processing_logs_page(
    *,
    page: int,
    page_size: int,
    stage: LogStage | None,
    status: LogStatus | None,
    meeting_id: ObjectId | None = None,
    message_contains: str | None = None,
) -> tuple[list[dict], int]:
    q: dict = {}
    if stage is not None:
        q["stage"] = stage.value
    if status is not None:
        q["status"] = status.value
    if meeting_id is not None:
        q["meeting_id"] = meeting_id
    if message_contains and message_contains.strip():
        q["message"] = {"$regex": re.escape(message_contains.strip()), "$options": "i"}
    coll = get_db().processing_logs
    total = await coll.count_documents(q)
    page = max(1, page)
    page_size = min(10, max(1, page_size))
    skip = (page - 1) * page_size
    cursor = coll.find(q).sort("timestamp", -1).skip(skip).limit(page_size)
    docs = await cursor.to_list(None)
    return docs, total
