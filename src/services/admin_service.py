"""Admin operations: user management, log queries, admin seeding — MongoDB version."""

import logging
import math
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.config import settings
from src.core import AuthorizationError, NotFoundError, ValidationError
from src.core.security import create_shadow_token, hash_password, validate_password_strength
from src.models.enums import AuthAction
from src.services.log_service import log_action

logger = logging.getLogger(__name__)


async def list_users(
    db: AsyncIOMotorDatabase,
    page: int = 1,
    page_size: int = 20,
    role: str | None = None,
    search: str | None = None,
    is_active: bool | None = None,
) -> dict:
    query: dict = {}

    if role:
        query["role"] = role
    if search:
        query["email"] = {"$regex": search, "$options": "i"}
    if is_active is not None:
        query["is_active"] = is_active

    total = await db.users.count_documents(query)

    offset = (page - 1) * page_size
    cursor = db.users.find(query).sort("created_at", -1).skip(offset).limit(page_size)
    users = await cursor.to_list(length=page_size)

    return {
        "items": [
            {
                "id": str(u["_id"]),
                "email": u["email"],
                "role": u["role"],
                "is_active": u.get("is_active", True),
                "is_email_verified": u.get("is_email_verified", False),
                "profile_completed": u.get("profile_completed", False),
                "created_at": u["created_at"].isoformat() if u.get("created_at") else None,
                "last_login_at": u["last_login_at"].isoformat() if u.get("last_login_at") else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


async def get_user(db: AsyncIOMotorDatabase, user_id: str) -> dict:
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise NotFoundError("User not found")

    user = await db.users.find_one({"_id": oid})
    if not user:
        raise NotFoundError("User not found")

    profile = user.get("profile")
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "is_active": user.get("is_active", True),
        "is_email_verified": user.get("is_email_verified", False),
        "profile_completed": user.get("profile_completed", False),
        "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
        "last_login_at": user["last_login_at"].isoformat() if user.get("last_login_at") else None,
        "profile": {
            "first_name": profile.get("first_name"),
            "last_name": profile.get("last_name"),
            "phone": profile.get("phone"),
            "company_name": profile.get("company_name"),
        } if profile else None,
    }


async def deactivate_user(
    db: AsyncIOMotorDatabase,
    admin: dict,
    user_id: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise NotFoundError("User not found")

    target = await db.users.find_one({"_id": oid})
    if not target:
        raise NotFoundError("User not found")

    if str(target["_id"]) == str(admin["_id"]):
        raise ValidationError("Cannot deactivate your own account")

    now = datetime.now(timezone.utc)
    await db.users.update_one({"_id": oid}, {"$set": {"is_active": False, "updated_at": now}})

    # Revoke all refresh tokens
    await db.refresh_tokens.update_many(
        {"user_id": oid, "revoked_at": None},
        {"$set": {"revoked_at": now}},
    )

    await log_action(
        db, AuthAction.ACCOUNT_DEACTIVATED,
        user_id=str(admin["_id"]), email=admin["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"target_user_id": user_id, "target_email": target["email"]},
    )

    return {"message": f"User {target['email']} has been deactivated"}


async def activate_user(
    db: AsyncIOMotorDatabase,
    admin: dict,
    user_id: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise NotFoundError("User not found")

    target = await db.users.find_one({"_id": oid})
    if not target:
        raise NotFoundError("User not found")

    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": oid},
        {"$set": {"is_active": True, "failed_login_count": 0, "locked_until": None, "updated_at": now}},
    )

    await log_action(
        db, AuthAction.ACCOUNT_ACTIVATED,
        user_id=str(admin["_id"]), email=admin["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"target_user_id": user_id, "target_email": target["email"]},
    )

    return {"message": f"User {target['email']} has been activated"}


async def get_auth_logs(
    db: AsyncIOMotorDatabase,
    page: int = 1,
    page_size: int = 50,
    user_id: str | None = None,
    action: str | None = None,
    email: str | None = None,
) -> dict:
    query: dict = {}

    if user_id:
        query["user_id"] = user_id
    if action:
        query["action"] = action
    if email:
        query["email"] = email

    total = await db.auth_logs.count_documents(query)

    offset = (page - 1) * page_size
    cursor = db.auth_logs.find(query).sort("created_at", -1).skip(offset).limit(page_size)
    logs = await cursor.to_list(length=page_size)

    return {
        "items": [
            {
                "id": str(log["_id"]),
                "user_id": log.get("user_id"),
                "action": log["action"],
                "email": log.get("email"),
                "ip_address": log.get("ip_address"),
                "user_agent": log.get("user_agent"),
                "metadata": log.get("metadata"),
                "created_at": log["created_at"].isoformat() if log.get("created_at") else None,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


async def seed_admin(db: AsyncIOMotorDatabase) -> bool:
    """Auto-seed admin user on startup if none exists. Returns True if created."""
    if not settings.admin_email or not settings.admin_password:
        logger.info("No ADMIN_EMAIL/ADMIN_PASSWORD set, skipping admin seed")
        return False

    existing = await db.users.find_one({"role": "admin"})
    if existing:
        logger.info("Admin user already exists, skipping seed")
        return False

    violations = validate_password_strength(settings.admin_password)
    if violations:
        logger.error("Admin password does not meet requirements: %s", violations)
        return False

    now = datetime.now(timezone.utc)
    admin_doc = {
        "email": settings.admin_email.lower(),
        "password_hash": hash_password(settings.admin_password),
        "role": "admin",
        "is_email_verified": True,
        "is_active": True,
        "profile_completed": True,
        "profile": {
            "first_name": "System",
            "last_name": "Administrator",
            "phone": None,
            "company_name": None,
            "avatar_url": None,
            "metadata": {},
        },
        "failed_login_count": 0,
        "locked_until": None,
        "last_login_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(admin_doc)

    logger.info("Admin user seeded: %s", settings.admin_email)
    return True


async def shadow_user(
    db: AsyncIOMotorDatabase,
    admin: dict,
    user_id: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    """Start a shadow session — admin acts as the target user."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise NotFoundError("User not found")

    target = await db.users.find_one({"_id": oid})
    if not target:
        raise NotFoundError("User not found")

    if not target.get("is_active"):
        raise ValidationError("Cannot shadow a deactivated user")

    if target["role"] == "admin":
        from src.core import AuthorizationError
        raise AuthorizationError("Cannot shadow another admin")

    shadow_token = create_shadow_token(
        target_user_id=str(target["_id"]),
        target_role=target["role"],
        target_email=target["email"],
        admin_id=str(admin["_id"]),
        admin_email=admin["email"],
    )

    # Build profile data
    profile = target.get("profile")
    profile_data = None
    if profile:
        profile_data = {
            "first_name": profile.get("first_name"),
            "last_name": profile.get("last_name"),
            "phone": profile.get("phone"),
            "company_name": profile.get("company_name"),
            "avatar_url": profile.get("avatar_url"),
            "metadata": profile.get("metadata", {}),
        }

    # Build agency data
    agency_data = None
    agency_doc = await db.agencies.find_one(
        {"members.user_id": oid},
        {"name": 1, "members.$": 1},
    )
    if agency_doc and agency_doc.get("members"):
        member = agency_doc["members"][0]
        agency_data = {
            "id": str(agency_doc["_id"]),
            "name": agency_doc.get("name"),
            "role_in_agency": member.get("role_in_agency", "member"),
        }

    await log_action(
        db, AuthAction.SHADOW_START,
        user_id=str(admin["_id"]), email=admin["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={
            "target_user_id": str(target["_id"]),
            "target_email": target["email"],
            "target_role": target["role"],
        },
    )

    return {
        "shadow_token": shadow_token,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "target_user": {
            "id": str(target["_id"]),
            "email": target["email"],
            "role": target["role"],
            "is_email_verified": target.get("is_email_verified", False),
            "profile_completed": target.get("profile_completed", False),
            "profile": profile_data,
            "agency": agency_data,
        },
        "message": f"Shadow session started for {target['email']}",
    }


async def end_shadow(
    db: AsyncIOMotorDatabase,
    admin: dict,
    shadowed_user_id: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    """Log the end of a shadow session."""
    target_email = "unknown"
    try:
        oid = ObjectId(shadowed_user_id)
        target = await db.users.find_one({"_id": oid}, {"email": 1})
        if target:
            target_email = target["email"]
    except Exception:
        pass

    await log_action(
        db, AuthAction.SHADOW_END,
        user_id=str(admin["_id"]), email=admin["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={
            "target_user_id": shadowed_user_id,
            "target_email": target_email,
        },
    )

    return {"message": "Shadow session ended"}
