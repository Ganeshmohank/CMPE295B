from fastapi import APIRouter, Body, Query
from pydantic import BaseModel

from app.schemas.action_item import (
    ActionItemOut,
    ActionItemRejectBody,
    ActionItemReviewDetailOut,
    ActionItemReviewOut,
    ActionItemUpdate,
    ReviewQueuePageOut,
)
from app.serializers import action_item_review_detail_row, action_item_review_row, action_item_to_out
from app.services import action_items as action_items_service

router = APIRouter()


class BulkResult(BaseModel):
    updated: int


@router.get("/review-queue", response_model=ReviewQueuePageOut)
async def review_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=10),
) -> ReviewQueuePageOut:
    rows, total_meetings, total_pending = await action_items_service.list_pending_review_paginated(
        page, page_size
    )
    return ReviewQueuePageOut(
        items=[ActionItemReviewOut(**action_item_review_row(r)) for r in rows],
        page=page,
        page_size=page_size,
        total_meetings=total_meetings,
        total_pending_items=total_pending,
    )


@router.get("/{item_id}/review-detail", response_model=ActionItemReviewDetailOut)
async def pending_review_item_detail(item_id: str) -> ActionItemReviewDetailOut:
    row = await action_items_service.get_pending_review_detail(item_id)
    return ActionItemReviewDetailOut(**action_item_review_detail_row(row))


@router.patch("/{item_id}", response_model=ActionItemOut)
async def patch_action_item(item_id: str, body: ActionItemUpdate) -> ActionItemOut:
    doc = await action_items_service.update_action_item(item_id, body)
    return ActionItemOut(**action_item_to_out(doc))


@router.post("/{item_id}/approve", response_model=ActionItemOut)
async def approve_item(item_id: str) -> ActionItemOut:
    doc = await action_items_service.approve_action_item(item_id)
    return ActionItemOut(**action_item_to_out(doc))


@router.post("/{item_id}/reject", response_model=ActionItemOut)
async def reject_item(
    item_id: str,
    body: ActionItemRejectBody | None = Body(default=None),
) -> ActionItemOut:
    _ = body
    doc = await action_items_service.reject_action_item(item_id)
    return ActionItemOut(**action_item_to_out(doc))


@router.post("/meetings/{meeting_id}/bulk-approve", response_model=BulkResult)
async def bulk_approve(meeting_id: str) -> BulkResult:
    n = await action_items_service.bulk_approve_for_meeting(meeting_id)
    return BulkResult(updated=n)


@router.post("/meetings/{meeting_id}/bulk-reject", response_model=BulkResult)
async def bulk_reject(meeting_id: str) -> BulkResult:
    n = await action_items_service.bulk_reject_for_meeting(meeting_id)
    return BulkResult(updated=n)
