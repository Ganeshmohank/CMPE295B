from enum import Enum


class MeetingStatus(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"
    FAILED = "failed"


class ProcessingStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PROCESSED = "processed"
    FAILED = "failed"


class ActionItemStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    TICKET_CREATED = "ticket_created"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LogStage(str, Enum):
    INGESTION = "ingestion"
    TRANSCRIPT_PROCESSING = "transcript_processing"
    EXTRACTION = "extraction"
    ASSIGNMENT = "assignment"
    NOTIFICATION = "notification"


class LogStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"
