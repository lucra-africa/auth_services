"""Notification triggers — convenience functions called from auth_service."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.services.notification_service import create_notification


async def on_signup(db: AsyncIOMotorDatabase, user_id, email: str) -> None:
    await create_notification(
        db,
        user_id=user_id,
        title="Welcome to Poruta!",
        message=f"Your account ({email}) has been created. Please verify your email to access all features.",
        notification_type="info",
        action_url="/settings",
    )


async def on_email_verified(db: AsyncIOMotorDatabase, user_id) -> None:
    await create_notification(
        db,
        user_id=user_id,
        title="Email verified",
        message="Your email has been verified. You now have full access to the platform.",
        notification_type="success",
    )


async def on_invitation_accepted(db: AsyncIOMotorDatabase, user_id, invited_by_email: str) -> None:
    await create_notification(
        db,
        user_id=user_id,
        title="Welcome to Poruta!",
        message=f"Your account has been created via invitation from {invited_by_email}.",
        notification_type="info",
    )


async def on_password_changed(db: AsyncIOMotorDatabase, user_id) -> None:
    await create_notification(
        db,
        user_id=user_id,
        title="Password changed",
        message="Your password was changed successfully. If you didn't do this, please contact support immediately.",
        notification_type="warning",
    )


async def on_profile_updated(db: AsyncIOMotorDatabase, user_id) -> None:
    await create_notification(
        db,
        user_id=user_id,
        title="Profile updated",
        message="Your profile information has been updated.",
        notification_type="success",
        action_url="/settings",
    )
