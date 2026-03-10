"""Admin operations: user management, log queries, admin seeding."""

import math
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.config import settings
from src.core import AuthorizationError, ConflictError, NotFoundError, ValidationError
from src.core.security import create_shadow_token, hash_password, validate_password_strength
from src.models.enums import AuthAction, UserRole
from src.models.log import AuthLog
from src.models.token import RefreshToken
from src.models.user import User, UserProfile
from src.services.log_service import log_action

import logging

logger = logging.getLogger(__name__)


async def list_users(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    role: str | None = None,
    search: str | None = None,
    is_active: bool | None = None,
) -> dict:
    query = select(User)

    if role:
        query = query.where(User.role == UserRole(role))
    if search:
        query = query.where(User.email.ilike(f"%{search}%"))
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = result.scalars().all()

    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role.value,
                "is_active": u.is_active,
                "is_email_verified": u.is_email_verified,
                "profile_completed": u.profile_completed,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


async def get_user(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User not found")

    # Load profile if exists
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()

    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
        "is_email_verified": user.is_email_verified,
        "profile_completed": user.profile_completed,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "profile": {
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "phone": profile.phone,
            "company_name": profile.company_name,
        } if profile else None,
    }


async def deactivate_user(
    db: AsyncSession,
    admin: User,
    user_id: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise NotFoundError("User not found")

    if str(target.id) == str(admin.id):
        raise ValidationError("Cannot deactivate your own account")

    target.is_active = False

    # Revoke all refresh tokens
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )

    await log_action(
        db, AuthAction.ACCOUNT_DEACTIVATED,
        user_id=str(admin.id), email=admin.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"target_user_id": user_id, "target_email": target.email},
    )

    return {"message": f"User {target.email} has been deactivated"}


async def activate_user(
    db: AsyncSession,
    admin: User,
    user_id: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise NotFoundError("User not found")

    target.is_active = True
    target.failed_login_count = 0
    target.locked_until = None

    await log_action(
        db, AuthAction.ACCOUNT_ACTIVATED,
        user_id=str(admin.id), email=admin.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"target_user_id": user_id, "target_email": target.email},
    )

    return {"message": f"User {target.email} has been activated"}


async def get_auth_logs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    user_id: str | None = None,
    action: str | None = None,
    email: str | None = None,
) -> dict:
    query = select(AuthLog)

    if user_id:
        query = query.where(AuthLog.user_id == user_id)
    if action:
        query = query.where(AuthLog.action == AuthAction(action))
    if email:
        query = query.where(AuthLog.email == email)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(AuthLog.created_at.desc()).offset(offset).limit(page_size)
    )
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(l.id),
                "user_id": str(l.user_id) if l.user_id else None,
                "action": l.action.value,
                "email": l.email,
                "ip_address": l.ip_address,
                "user_agent": l.user_agent,
                "metadata": l.metadata_,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


async def seed_admin(db: AsyncSession) -> bool:
    """Auto-seed admin user on startup if none exists. Returns True if created."""
    if not settings.admin_email or not settings.admin_password:
        logger.info("No ADMIN_EMAIL/ADMIN_PASSWORD set, skipping admin seed")
        return False

    result = await db.execute(
        select(User).where(User.role == UserRole.ADMIN).limit(1)
    )
    if result.scalar_one_or_none():
        logger.info("Admin user already exists, skipping seed")
        return False

    violations = validate_password_strength(settings.admin_password)
    if violations:
        logger.error("Admin password does not meet requirements: %s", violations)
        return False

    admin = User(
        email=settings.admin_email.lower(),
        password_hash=hash_password(settings.admin_password),
        role=UserRole.ADMIN,
        is_email_verified=True,
        is_active=True,
        profile_completed=True,
    )
    db.add(admin)
    await db.flush()

    profile = UserProfile(
        user_id=admin.id,
        first_name="System",
        last_name="Administrator",
        metadata_={},
    )
    db.add(profile)
    await db.flush()

    logger.info("Admin user seeded: %s", admin.email)
    return True


async def shadow_user(
    db: AsyncSession,
    admin: User,
    user_id: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    """Start a shadow session — admin acts as the target user."""
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(joinedload(User.profile), selectinload(User.agency_links))
    )
    target = result.unique().scalar_one_or_none()
    if not target:
        raise NotFoundError("User not found")

    if not target.is_active:
        raise ValidationError("Cannot shadow a deactivated user")

    if target.role == UserRole.ADMIN:
        raise AuthorizationError("Cannot shadow another admin")

    shadow_token = create_shadow_token(
        target_user_id=str(target.id),
        target_role=target.role.value,
        target_email=target.email,
        admin_id=str(admin.id),
        admin_email=admin.email,
    )

    # Build profile dict if the user has completed their profile
    profile_data = None
    if target.profile:
        profile_data = {
            "first_name": target.profile.first_name,
            "last_name": target.profile.last_name,
            "phone": target.profile.phone,
            "company_name": target.profile.company_name,
            "avatar_url": target.profile.avatar_url,
            "metadata": target.profile.metadata_ or {},
        }

    # Build agency dict from the first agency link (if any)
    agency_data = None
    if target.agency_links:
        link = target.agency_links[0]
        agency_data = {
            "id": str(link.agency_id),
            "name": None,
            "role_in_agency": link.role_in_agency.value if link.role_in_agency else "member",
        }

    # Log AFTER all reads so a log failure can't poison the session
    await log_action(
        db, AuthAction.SHADOW_START,
        user_id=str(admin.id), email=admin.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={
            "target_user_id": str(target.id),
            "target_email": target.email,
            "target_role": target.role.value,
        },
    )

    return {
        "shadow_token": shadow_token,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "target_user": {
            "id": str(target.id),
            "email": target.email,
            "role": target.role.value,
            "is_email_verified": target.is_email_verified,
            "profile_completed": target.profile_completed,
            "profile": profile_data,
            "agency": agency_data,
        },
        "message": f"Shadow session started for {target.email}",
    }


async def end_shadow(
    db: AsyncSession,
    admin: User,
    shadowed_user_id: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    """Log the end of a shadow session."""
    result = await db.execute(select(User).where(User.id == shadowed_user_id))
    target = result.scalar_one_or_none()

    await log_action(
        db, AuthAction.SHADOW_END,
        user_id=str(admin.id), email=admin.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={
            "target_user_id": shadowed_user_id,
            "target_email": target.email if target else "unknown",
        },
    )

    return {"message": "Shadow session ended"}
