import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.models.enums import AuthAction

logger = logging.getLogger(__name__)


async def log_action(
    db: AsyncIOMotorDatabase,
    action: AuthAction,
    user_id: str | None = None,
    email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Write a structured auth log entry. Best-effort — never raises."""
    try:
        await db.auth_logs.insert_one({
            "user_id": user_id,
            "action": action.value,
            "email": email,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "metadata": metadata,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        logger.exception("Failed to write auth log entry: action=%s email=%s", action, email)


def get_client_ip(request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None
