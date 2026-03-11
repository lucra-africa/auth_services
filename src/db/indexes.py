"""MongoDB index definitions for all auth collections."""

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    # ── users ──
    await db.users.create_index("email", unique=True)
    await db.users.create_index("role")
    await db.users.create_index("is_active")

    # ── agencies ──
    await db.agencies.create_index("registration_number", unique=True)
    await db.agencies.create_index("created_by")

    # ── email_verification_tokens ──
    await db.email_verification_tokens.create_index("token_hash", unique=True)
    await db.email_verification_tokens.create_index("user_id")

    # ── password_reset_tokens ──
    await db.password_reset_tokens.create_index("token_hash", unique=True)
    await db.password_reset_tokens.create_index("user_id")

    # ── refresh_tokens ──
    await db.refresh_tokens.create_index("token_hash", unique=True)
    await db.refresh_tokens.create_index("user_id")

    # ── invitation_tokens ──
    await db.invitation_tokens.create_index("token_hash", unique=True)
    await db.invitation_tokens.create_index("email")
    await db.invitation_tokens.create_index("invited_by")

    # ── auth_logs ──
    await db.auth_logs.create_index([("created_at", DESCENDING)])
    await db.auth_logs.create_index("user_id")
    await db.auth_logs.create_index("action")
    await db.auth_logs.create_index("email")

    # ── notifications ──
    await db.notifications.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    await db.notifications.create_index([("user_id", ASCENDING), ("read", ASCENDING)])

    # ── threads ──
    await db.threads.create_index("participant_ids")
    await db.threads.create_index([("updated_at", DESCENDING)])

    # ── messages ──
    await db.messages.create_index([("thread_id", ASCENDING), ("created_at", ASCENDING)])
    await db.messages.create_index("sender_id")
