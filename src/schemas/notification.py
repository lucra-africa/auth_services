"""Pydantic schemas for the notification system."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── Request schemas ─────────────────────────────────────────────────

class CreateNotificationRequest(BaseModel):
    user_id: str
    title: str = Field(..., max_length=255)
    message: str = Field(..., max_length=2000)
    notification_type: str = Field(default="info", pattern="^(info|success|warning|error|payment)$")
    action_url: str | None = None


class PushNotificationRequest(BaseModel):
    """For external services to push notifications via API key."""
    user_id: str
    title: str = Field(..., max_length=255)
    message: str = Field(..., max_length=2000)
    notification_type: str = Field(default="info", pattern="^(info|success|warning|error|payment)$")
    action_url: str | None = None


# ── Response schemas ────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    notification_type: str
    read: bool
    action_url: str | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int
    page: int
    page_size: int
    pages: int
