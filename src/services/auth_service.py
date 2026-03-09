"""Core authentication business logic."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core import (
    AccountLockedError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from src.core.security import (
    create_access_token,
    create_refresh_token_jwt,
    decode_token,
    generate_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from src.models.enums import AgencyRole, AuthAction, UserRole
from src.models.token import (
    EmailVerificationToken,
    InvitationToken,
    PasswordResetToken,
    RefreshToken,
)
from src.models.user import User, UserProfile
from src.models.agency import Agency, UserAgency
from src.services import email_service
from src.services.log_service import log_action

logger = logging.getLogger(__name__)

INVITATION_PERMISSIONS: dict[str, list[str]] = {
    "agency_manager": ["agent"],
    "government": ["inspector"],
    "admin": ["government"],
}


# ── Helpers ──────────────────────────────────────────────────────────

def _build_user_response(user: User) -> dict:
    """Build user dict for API responses."""
    profile_data = None
    if user.profile:
        profile_data = {
            "first_name": user.profile.first_name,
            "last_name": user.profile.last_name,
            "phone": user.profile.phone,
            "company_name": user.profile.company_name,
            "avatar_url": user.profile.avatar_url,
            "metadata": user.profile.metadata_,
        }

    agency_data = None
    if user.agency_links:
        link = user.agency_links[0]
        agency_data = {
            "id": str(link.agency_id),
            "name": link.agency.name if link.agency else None,
            "role_in_agency": link.role_in_agency.value,
        }

    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "is_email_verified": user.is_email_verified,
        "profile_completed": user.profile_completed,
        "profile": profile_data,
        "agency": agency_data,
    }


def _build_token_response(user: User, access_token: str, refresh_token: str) -> dict:
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": _build_user_response(user),
    }


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _create_token_pair(
    db: AsyncSession, user: User, ip_address: str | None = None, user_agent_str: str | None = None
) -> tuple[str, str]:
    access = create_access_token(str(user.id), user.role.value, user.email)
    refresh = create_refresh_token_jwt(str(user.id))

    refresh_hash = hash_token(refresh)
    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        ip_address=ip_address,
        device_info=user_agent_str[:255] if user_agent_str else None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days),
    )
    db.add(rt)
    await db.flush()
    return access, refresh


# ── Signup ──────────────────────────────────────────────────────────

async def signup(
    db: AsyncSession,
    email: str,
    password: str,
    role: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    violations = validate_password_strength(password)
    if violations:
        raise ValidationError("Password does not meet requirements", details=violations)

    existing = await _get_user_by_email(db, email)
    if existing:
        raise ConflictError("Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(password),
        role=UserRole(role),
        is_email_verified=False,
        is_active=True,
        profile_completed=False,
    )
    db.add(user)
    await db.flush()

    raw_token = generate_token()
    evt = EmailVerificationToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(evt)
    await db.flush()

    await email_service.send_verification_email(email, raw_token)

    await log_action(
        db, AuthAction.SIGNUP,
        user_id=str(user.id), email=email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"role": role},
    )

    return {"message": "Account created. Please check your email to verify your account.", "email": email}


# ── Email Verification ──────────────────────────────────────────────

async def verify_email(
    db: AsyncSession, token: str, ip_address: str | None = None, user_agent_str: str | None = None
) -> dict:
    token_hash = hash_token(token)
    result = await db.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
    )
    evt = result.scalar_one_or_none()

    if not evt:
        raise ValidationError("Invalid verification token")
    if evt.used_at:
        raise ValidationError("Token has already been used")
    if evt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValidationError("Verification token has expired. Please request a new one.")

    evt.used_at = datetime.now(timezone.utc)

    result = await db.execute(select(User).where(User.id == evt.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User not found")

    user.is_email_verified = True

    await log_action(
        db, AuthAction.EMAIL_VERIFY,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
    )

    return {"message": "Email verified successfully. You can now log in."}


async def resend_verification(
    db: AsyncSession, email: str, ip_address: str | None = None, user_agent_str: str | None = None
) -> dict:
    user = await _get_user_by_email(db, email)

    if user and user.is_active and not user.is_email_verified:
        # Invalidate old tokens
        await db.execute(
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(timezone.utc))
        )

        raw_token = generate_token()
        evt = EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(evt)
        await db.flush()

        await email_service.send_verification_email(email, raw_token)

    return {"message": "If an unverified account exists, a new verification email has been sent."}


# ── Login ────────────────────────────────────────────────────────────

async def login(
    db: AsyncSession,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    user = await _get_user_by_email(db, email)

    if not user:
        await log_action(
            db, AuthAction.FAILED_LOGIN, email=email,
            ip_address=ip_address, user_agent=user_agent_str,
            metadata={"reason": "user_not_found"},
        )
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("Account has been deactivated. Contact support.")

    # Check lockout
    now = datetime.now(timezone.utc)
    if user.locked_until:
        lock_time = user.locked_until.replace(tzinfo=timezone.utc) if user.locked_until.tzinfo is None else user.locked_until
        if lock_time > now:
            minutes_left = int((lock_time - now).total_seconds() / 60) + 1
            raise AccountLockedError(
                f"Account locked due to too many failed attempts. Try again in {minutes_left} minutes.",
                locked_until=lock_time.isoformat(),
            )
        else:
            user.failed_login_count = 0
            user.locked_until = None

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        attempt = user.failed_login_count

        await log_action(
            db, AuthAction.FAILED_LOGIN,
            user_id=str(user.id), email=email,
            ip_address=ip_address, user_agent=user_agent_str,
            metadata={"attempt": attempt, "reason": "wrong_password"},
        )

        if attempt >= 5:
            user.locked_until = now + timedelta(minutes=15)
            await log_action(
                db, AuthAction.ACCOUNT_LOCKED,
                user_id=str(user.id), email=email,
                ip_address=ip_address, user_agent=user_agent_str,
                metadata={"failed_attempts": attempt, "lockout_duration_minutes": 15},
            )
            await db.flush()
            raise AccountLockedError(
                "Account locked due to too many failed attempts. Try again in 15 minutes.",
                locked_until=user.locked_until.isoformat(),
            )

        await db.flush()
        raise AuthenticationError("Invalid email or password")

    if not user.is_email_verified:
        raise AuthorizationError("Please verify your email address before logging in.")

    # Success
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    access, refresh = await _create_token_pair(db, user, ip_address, user_agent_str)

    await log_action(
        db, AuthAction.LOGIN,
        user_id=str(user.id), email=email,
        ip_address=ip_address, user_agent=user_agent_str,
    )

    return _build_token_response(user, access, refresh)


# ── Token Refresh ────────────────────────────────────────────────────

async def refresh_tokens(
    db: AsyncSession,
    refresh_token_str: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    payload = decode_token(refresh_token_str)
    if payload.get("type") != "refresh":
        raise AuthenticationError("Invalid token type")

    token_hash = hash_token(refresh_token_str)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if not stored:
        raise AuthenticationError("Invalid refresh token")
    if stored.revoked_at:
        raise AuthenticationError("Token has been revoked")
    now = datetime.now(timezone.utc)
    expires = stored.expires_at.replace(tzinfo=timezone.utc) if stored.expires_at.tzinfo is None else stored.expires_at
    if expires <= now:
        raise AuthenticationError("Refresh token has expired")

    result = await db.execute(select(User).where(User.id == stored.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise AuthenticationError("User not found or deactivated")

    # Rotate
    stored.revoked_at = now
    access, new_refresh = await _create_token_pair(db, user, ip_address, user_agent_str)

    await log_action(
        db, AuthAction.TOKEN_REFRESH,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
    )

    return _build_token_response(user, access, new_refresh)


# ── Logout ───────────────────────────────────────────────────────────

async def logout(
    db: AsyncSession,
    user: User,
    refresh_token_str: str | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if refresh_token_str:
        token_hash = hash_token(refresh_token_str)
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == user.id,
            )
        )
        stored = result.scalar_one_or_none()
        if stored and not stored.revoked_at:
            stored.revoked_at = datetime.now(timezone.utc)

    await log_action(
        db, AuthAction.LOGOUT,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
    )

    return {"message": "Logged out successfully"}


# ── Invitation ───────────────────────────────────────────────────────

async def send_invitation(
    db: AsyncSession,
    inviter: User,
    email: str,
    role: str,
    agency_id: str | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    allowed_targets = INVITATION_PERMISSIONS.get(inviter.role.value, [])
    if role not in allowed_targets:
        raise AuthorizationError(f"Role '{inviter.role.value}' cannot invite '{role}' users")

    existing_user = await _get_user_by_email(db, email)
    if existing_user:
        raise ConflictError("A user with this email already exists")

    # Check for pending invitation
    result = await db.execute(
        select(InvitationToken).where(
            InvitationToken.email == email,
            InvitationToken.used_at.is_(None),
            InvitationToken.expires_at > datetime.now(timezone.utc),
        )
    )
    if result.scalar_one_or_none():
        raise ConflictError("An active invitation already exists for this email")

    resolved_agency_id = None
    agency_name = None

    if role == "agent":
        if not agency_id:
            raise ValidationError("agency_id is required when inviting an agent")
        result = await db.execute(select(Agency).where(Agency.id == agency_id))
        agency = result.scalar_one_or_none()
        if not agency:
            raise NotFoundError("Agency not found")
        if not agency.is_active:
            raise ValidationError("Agency has been deactivated")

        # Verify inviter belongs to this agency
        result = await db.execute(
            select(UserAgency).where(
                UserAgency.user_id == inviter.id,
                UserAgency.agency_id == agency.id,
            )
        )
        if not result.scalar_one_or_none():
            raise AuthorizationError("You can only invite agents to your own agency")

        resolved_agency_id = agency.id
        agency_name = agency.name

    raw_token = generate_token()
    invitation = InvitationToken(
        token_hash=hash_token(raw_token),
        email=email,
        role=UserRole(role),
        invited_by=inviter.id,
        agency_id=resolved_agency_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(invitation)
    await db.flush()

    # Get inviter name
    inviter_name = "Administrator"
    if inviter.profile:
        inviter_name = f"{inviter.profile.first_name} {inviter.profile.last_name}"

    await email_service.send_invitation_email(email, raw_token, inviter_name, role, agency_name)

    await log_action(
        db, AuthAction.INVITATION_SENT,
        user_id=str(inviter.id), email=inviter.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"invited_email": email, "role": role, "agency_id": str(resolved_agency_id) if resolved_agency_id else None},
    )

    return {
        "message": f"Invitation sent to {email}",
        "expires_at": invitation.expires_at.isoformat(),
    }


async def validate_invitation(db: AsyncSession, token: str) -> dict:
    token_hash = hash_token(token)
    result = await db.execute(
        select(InvitationToken).where(InvitationToken.token_hash == token_hash)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise ValidationError("Invalid invitation token")
    if invitation.used_at:
        raise ValidationError("This invitation has already been used")
    if invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValidationError("Invitation has expired. Please contact your administrator.")

    # Get inviter info
    result = await db.execute(select(User).where(User.id == invitation.invited_by))
    inviter = result.scalar_one_or_none()
    inviter_info = {"name": "Unknown", "email": ""}
    if inviter and inviter.profile:
        inviter_info = {
            "name": f"{inviter.profile.first_name} {inviter.profile.last_name}",
            "email": inviter.email,
        }

    agency_info = None
    if invitation.agency_id:
        result = await db.execute(select(Agency).where(Agency.id == invitation.agency_id))
        agency = result.scalar_one_or_none()
        if agency:
            agency_info = {"id": str(agency.id), "name": agency.name}

    return {
        "email": invitation.email,
        "role": invitation.role.value,
        "invited_by": inviter_info,
        "agency": agency_info,
    }


async def signup_invited(
    db: AsyncSession,
    token: str,
    password: str,
    first_name: str,
    last_name: str,
    phone: str | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    token_hash = hash_token(token)
    result = await db.execute(
        select(InvitationToken).where(InvitationToken.token_hash == token_hash)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise ValidationError("Invalid invitation token")
    if invitation.used_at:
        raise ValidationError("This invitation has already been used")
    if invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValidationError("Invitation has expired. Please contact your administrator.")

    violations = validate_password_strength(password)
    if violations:
        raise ValidationError("Password does not meet requirements", details=violations)

    existing = await _get_user_by_email(db, invitation.email)
    if existing:
        raise ConflictError("A user with this email already exists")

    user = User(
        email=invitation.email,
        password_hash=hash_password(password),
        role=invitation.role,
        is_email_verified=True,
        is_active=True,
        profile_completed=True,
    )
    db.add(user)
    await db.flush()

    profile = UserProfile(
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        metadata_={},
    )
    db.add(profile)

    if invitation.role == UserRole.AGENT and invitation.agency_id:
        ua = UserAgency(
            user_id=user.id,
            agency_id=invitation.agency_id,
            role_in_agency=AgencyRole.AGENT,
        )
        db.add(ua)

    invitation.used_at = datetime.now(timezone.utc)
    await db.flush()

    # Reload user with relationships
    result = await db.execute(select(User).where(User.id == user.id))
    user = result.scalar_one()

    access, refresh = await _create_token_pair(db, user, ip_address, user_agent_str)

    await log_action(
        db, AuthAction.INVITATION_USED,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"invited_by": str(invitation.invited_by), "role": invitation.role.value},
    )
    await log_action(
        db, AuthAction.SIGNUP,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"role": invitation.role.value, "via": "invitation"},
    )

    return _build_token_response(user, access, refresh)


# ── Profile ──────────────────────────────────────────────────────────

async def complete_profile(
    db: AsyncSession,
    user: User,
    first_name: str,
    last_name: str,
    phone: str | None = None,
    company_name: str | None = None,
    agency_id: str | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if user.profile_completed:
        raise ValidationError("Profile has already been completed")

    if user.role == UserRole.IMPORTER and not company_name:
        raise ValidationError("company_name is required for importers")

    if user.role == UserRole.AGENCY_MANAGER:
        if not agency_id:
            raise ValidationError("agency_id is required for agency managers")
        result = await db.execute(select(Agency).where(Agency.id == agency_id))
        agency = result.scalar_one_or_none()
        if not agency:
            raise NotFoundError("Agency not found")
        if not agency.is_active:
            raise ValidationError("Agency has been deactivated")

    profile = UserProfile(
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        company_name=company_name if user.role == UserRole.IMPORTER else None,
        metadata_={},
    )
    db.add(profile)

    if user.role == UserRole.AGENCY_MANAGER and agency_id:
        ua = UserAgency(
            user_id=user.id,
            agency_id=agency_id,
            role_in_agency=AgencyRole.MANAGER,
        )
        db.add(ua)

    user.profile_completed = True
    await db.flush()

    # Reload
    result = await db.execute(select(User).where(User.id == user.id))
    user = result.scalar_one()

    await log_action(
        db, AuthAction.PROFILE_UPDATED,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"fields_set": ["first_name", "last_name", "phone", "company_name" if company_name else None]},
    )

    return {"message": "Profile completed successfully", "user": _build_user_response(user)}


async def get_profile(db: AsyncSession, user: User) -> dict:
    return _build_user_response(user)


async def update_profile(
    db: AsyncSession,
    user: User,
    data: dict,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if not user.profile:
        raise NotFoundError("Profile not found")

    changed = []
    for field in ("first_name", "last_name", "phone", "company_name"):
        if field in data and data[field] is not None:
            setattr(user.profile, field, data[field])
            changed.append(field)

    await db.flush()

    result = await db.execute(select(User).where(User.id == user.id))
    user = result.scalar_one()

    await log_action(
        db, AuthAction.PROFILE_UPDATED,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"fields_changed": changed},
    )

    return {"message": "Profile updated", "user": _build_user_response(user)}


# ── Password Management ─────────────────────────────────────────────

async def forgot_password(
    db: AsyncSession,
    email: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    user = await _get_user_by_email(db, email)

    if user and user.is_active and user.is_email_verified:
        # Invalidate existing tokens
        await db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(timezone.utc))
        )

        raw_token = generate_token()
        prt = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(prt)
        await db.flush()

        await email_service.send_password_reset_email(email, raw_token)

        await log_action(
            db, AuthAction.PASSWORD_RESET_REQUESTED,
            user_id=str(user.id), email=email,
            ip_address=ip_address, user_agent=user_agent_str,
        )

    return {"message": "If an account exists with this email, a password reset link has been sent."}


async def reset_password(
    db: AsyncSession,
    token: str,
    new_password: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    token_hash = hash_token(token)
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    prt = result.scalar_one_or_none()

    if not prt:
        raise ValidationError("Invalid or expired reset token")
    if prt.used_at:
        raise ValidationError("Token has already been used")
    if prt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValidationError("Reset token has expired. Please request a new one.")

    violations = validate_password_strength(new_password)
    if violations:
        raise ValidationError("Password does not meet requirements", details=violations)

    result = await db.execute(select(User).where(User.id == prt.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise ValidationError("Account not found or deactivated")

    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    prt.used_at = datetime.now(timezone.utc)

    # Revoke all refresh tokens
    now = datetime.now(timezone.utc)
    revoke_result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    await log_action(
        db, AuthAction.PASSWORD_RESET,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"sessions_revoked": revoke_result.rowcount},
    )

    return {"message": "Password has been reset successfully. Please log in with your new password."}


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect")

    if current_password == new_password:
        raise ValidationError("New password must be different from current password")

    violations = validate_password_strength(new_password)
    if violations:
        raise ValidationError("Password does not meet requirements", details=violations)

    user.password_hash = hash_password(new_password)

    # Revoke all refresh tokens
    now = datetime.now(timezone.utc)
    revoke_result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    await db.flush()

    # Issue new tokens for current session
    access, refresh = await _create_token_pair(db, user, ip_address, user_agent_str)

    await log_action(
        db, AuthAction.PASSWORD_CHANGED,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"other_sessions_revoked": revoke_result.rowcount},
    )

    return {
        "message": "Password changed successfully. Other sessions have been logged out.",
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
    }
