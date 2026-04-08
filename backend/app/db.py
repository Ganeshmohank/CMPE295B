from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.database_name]


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


async def ensure_indexes() -> None:
    db = get_db()
    await db.projects.create_index("name")
    await db.meetings.create_index("start_time")
    await db.meetings.create_index("project_id")
    await db.meetings.create_index("status")
    await db.meetings.create_index("processing_status")
    await db.meetings.create_index("zoom_meeting_id", unique=True, sparse=True)
    await db.transcripts.create_index("meeting_id", unique=True)
    await db.action_items.create_index("meeting_id")
    await db.action_items.create_index("status")
    await db.processing_logs.create_index("meeting_id")
    await db.processing_logs.create_index([("timestamp", -1)])
    await db.meeting_participants.create_index([("meeting_id", 1), ("participant_id", 1)], unique=True)
    await db.participants.create_index("email", unique=True, sparse=True)
