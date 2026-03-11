"""Notification API routes."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.config import settings
from src.core.dependencies import get_current_user
from src.core import AuthenticationError
from src.db.mongo import get_db
from src.schemas.notification import PushNotificationRequest
from src.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── User-facing endpoints ──────────────────────────────────────────

@router.get("")
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    unread_only: bool = Query(False),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await notification_service.list_notifications(
        db, user_id=user["_id"], page=page, page_size=page_size, unread_only=unread_only,
    )


@router.get("/unread-count")
async def unread_count(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await notification_service.get_unread_count(db, user_id=user["_id"])


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await notification_service.mark_read(db, notification_id=notification_id, user_id=user["_id"])


@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await notification_service.mark_all_read(db, user_id=user["_id"])


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await notification_service.delete_notification(db, notification_id=notification_id, user_id=user["_id"])


@router.delete("")
async def clear_all(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await notification_service.clear_all(db, user_id=user["_id"])


# ── External push endpoint (API key auth) ──────────────────────────

@router.post("/push")
async def push_notification(
    body: PushNotificationRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Push a notification from an external service (e.g. poruta-backend).
    Requires the X-API-Key header matching NOTIFICATION_API_KEY env var."""
    if not settings.notification_api_key or not secrets.compare_digest(
        x_api_key, settings.notification_api_key
    ):
        raise AuthenticationError("Invalid API key")

    result = await notification_service.create_notification(
        db,
        user_id=body.user_id,
        title=body.title,
        message=body.message,
        notification_type=body.notification_type,
        action_url=body.action_url,
    )
    return result
