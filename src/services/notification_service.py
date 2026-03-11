"""Notification service — MongoDB version."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_notification(
    db: AsyncIOMotorDatabase,
    *,
    user_id,
    title: str,
    message: str,
    notification_type: str = "info",
    action_url: str | None = None,
) -> dict:
    """Create a notification for a user."""
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)

    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "notification_type": notification_type,
        "read": False,
        "action_url": action_url,
        "created_at": now,
    }
    result = await db.notifications.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _build_response(doc)


async def list_notifications(
    db: AsyncIOMotorDatabase,
    *,
    user_id,
    page: int = 1,
    page_size: int = 30,
    unread_only: bool = False,
) -> dict:
    """List notifications for a user."""
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)

    query: dict = {"user_id": user_id}
    if unread_only:
        query["read"] = False

    total = await db.notifications.count_documents(query)
    unread_count = await db.notifications.count_documents({"user_id": user_id, "read": False})

    cursor = (
        db.notifications.find(query)
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    notifications = await cursor.to_list(length=page_size)

    return {
        "items": [_build_response(n) for n in notifications],
        "total": total,
        "unread_count": unread_count,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


async def mark_read(db: AsyncIOMotorDatabase, *, notification_id, user_id) -> dict:
    """Mark a single notification as read."""
    if isinstance(notification_id, str):
        notification_id = ObjectId(notification_id)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)

    result = await db.notifications.update_one(
        {"_id": notification_id, "user_id": user_id},
        {"$set": {"read": True}},
    )
    if result.matched_count == 0:
        from src.core import NotFoundError
        raise NotFoundError("Notification not found")
    return {"message": "Marked as read"}


async def mark_all_read(db: AsyncIOMotorDatabase, *, user_id) -> dict:
    """Mark all notifications as read for a user."""
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)

    result = await db.notifications.update_many(
        {"user_id": user_id, "read": False},
        {"$set": {"read": True}},
    )
    return {"message": f"Marked {result.modified_count} notifications as read"}


async def delete_notification(db: AsyncIOMotorDatabase, *, notification_id, user_id) -> dict:
    """Delete a notification."""
    if isinstance(notification_id, str):
        notification_id = ObjectId(notification_id)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)

    result = await db.notifications.delete_one({"_id": notification_id, "user_id": user_id})
    if result.deleted_count == 0:
        from src.core import NotFoundError
        raise NotFoundError("Notification not found")
    return {"message": "Notification deleted"}


async def clear_all(db: AsyncIOMotorDatabase, *, user_id) -> dict:
    """Delete all notifications for a user."""
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)

    result = await db.notifications.delete_many({"user_id": user_id})
    return {"message": f"Deleted {result.deleted_count} notifications"}


async def get_unread_count(db: AsyncIOMotorDatabase, *, user_id) -> dict:
    """Get the unread notification count for badge display."""
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)

    count = await db.notifications.count_documents({"user_id": user_id, "read": False})
    return {"unread_count": count}


def _build_response(notif: dict) -> dict:
    return {
        "id": str(notif["_id"]),
        "title": notif["title"],
        "message": notif["message"],
        "notification_type": notif.get("notification_type", "info"),
        "read": notif.get("read", False),
        "action_url": notif.get("action_url"),
        "created_at": notif["created_at"].isoformat(),
    }
