"""Core authentication business logic — MongoDB version."""

import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

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
from src.models.enums import AuthAction
from src.services import email_service
from src.services.log_service import log_action

logger = logging.getLogger(__name__)

INVITATION_PERMISSIONS: dict[str, list[str]] = {
    "agency_manager": ["agent"],
    "government_rra": ["government_rra"],
    "government_rsb": ["government_rsb"],
    "admin": ["importer", "agent", "agency_manager", "inspector", "government_rra", "government_rsb"],
}


# ── Helpers ──────────────────────────────────────────────────────────

def _build_user_response(user: dict) -> dict:
    """Build user dict for API responses. `user` is a MongoDB document."""
    profile = user.get("profile")
    profile_data = None
    if profile:
        profile_data = {
            "first_name": profile.get("first_name"),
            "last_name": profile.get("last_name"),
            "phone": profile.get("phone"),
            "phone_number": profile.get("phone_number"),
            "company_name": profile.get("company_name"),
            "avatar_url": profile.get("avatar_url"),
            "address": profile.get("address"),
            "metadata": profile.get("metadata", {}),
        }

    agency_data = None
    if user.get("agency"):
        ag = user["agency"]
        agency_data = {
            "id": str(ag["agency_id"]),
            "name": ag.get("name"),
            "role_in_agency": ag.get("role_in_agency"),
        }

    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "is_email_verified": user.get("is_email_verified", False),
        "profile_completed": user.get("profile_completed", False),
        "phone_number": user.get("phone_number"),
        "address": user.get("address"),
        "profile": profile_data,
        "agency": agency_data,
    }


def _build_token_response(user: dict, access_token: str, refresh_token: str) -> dict:
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": _build_user_response(user),
    }


async def _get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> dict | None:
    return await db.users.find_one({"email": email})


async def _create_token_pair(
    db: AsyncIOMotorDatabase, user: dict, ip_address: str | None = None, user_agent_str: str | None = None
) -> tuple[str, str]:
    user_id_str = str(user["_id"])
    access = create_access_token(user_id_str, user["role"], user["email"])
    refresh = create_refresh_token_jwt(user_id_str)

    refresh_hash = hash_token(refresh)
    now = datetime.now(timezone.utc)
    await db.refresh_tokens.insert_one({
        "user_id": user["_id"],
        "token_hash": refresh_hash,
        "ip_address": ip_address,
        "device_info": user_agent_str[:255] if user_agent_str else None,
        "expires_at": now + timedelta(days=settings.jwt_refresh_token_expire_days),
        "revoked_at": None,
        "created_at": now,
    })
    return access, refresh


async def _reload_user(db: AsyncIOMotorDatabase, user_id: ObjectId) -> dict:
    """Reload user with agency lookup for response building."""
    user = await db.users.find_one({"_id": user_id})
    if user:
        # Lookup agency membership
        agency_doc = await db.agencies.find_one(
            {"members.user_id": user_id},
            {"name": 1, "members.$": 1},
        )
        if agency_doc and agency_doc.get("members"):
            member = agency_doc["members"][0]
            user["agency"] = {
                "agency_id": agency_doc["_id"],
                "name": agency_doc.get("name"),
                "role_in_agency": member.get("role_in_agency"),
            }
    return user


# ── Signup ──────────────────────────────────────────────────────────

async def signup(
    db: AsyncIOMotorDatabase,
    email: str,
    password: str,
    role: str,
    phone_number: str | None = None,
    address: dict | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    violations = validate_password_strength(password)
    if violations:
        raise ValidationError("Password does not meet requirements", details=violations)

    existing = await _get_user_by_email(db, email)
    if existing:
        raise ConflictError("Email already registered")

    now = datetime.now(timezone.utc)
    user_doc = {
        "email": email,
        "password_hash": hash_password(password),
        "role": role,
        "is_email_verified": False,
        "is_active": True,
        "profile_completed": False,
        "profile": None,
        "phone_number": phone_number,
        "address": address,
        "failed_login_count": 0,
        "locked_until": None,
        "last_login_at": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.users.insert_one(user_doc)
    user_id = result.inserted_id

    # Generate email verification token
    raw_token = generate_token()
    await db.email_verification_tokens.insert_one({
        "user_id": user_id,
        "token_hash": hash_token(raw_token),
        "expires_at": now + timedelta(hours=24),
        "used_at": None,
        "created_at": now,
    })

    await email_service.send_verification_email(email, raw_token)

    await log_action(
        db, AuthAction.SIGNUP,
        user_id=str(user_id), email=email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"role": role},
    )

    from src.services.notification_triggers import on_signup
    await on_signup(db, user_id, email)

    return {"message": "Account created successfully. Please check your email to verify your address.", "email": email}


# ── Email Verification ──────────────────────────────────────────────

async def verify_email(
    db: AsyncIOMotorDatabase, token: str, ip_address: str | None = None, user_agent_str: str | None = None
) -> dict:
    token_hash = hash_token(token)
    evt = await db.email_verification_tokens.find_one({"token_hash": token_hash})

    if not evt:
        raise ValidationError("Invalid verification token")
    if evt.get("used_at"):
        raise ValidationError("Token has already been used")
    if evt["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValidationError("Verification token has expired. Please request a new one.")

    now = datetime.now(timezone.utc)
    await db.email_verification_tokens.update_one(
        {"_id": evt["_id"]}, {"$set": {"used_at": now}}
    )

    user = await db.users.find_one({"_id": evt["user_id"]})
    if not user:
        raise NotFoundError("User not found")

    await db.users.update_one(
        {"_id": user["_id"]}, {"$set": {"is_email_verified": True, "updated_at": now}}
    )

    await log_action(
        db, AuthAction.EMAIL_VERIFY,
        user_id=str(user["_id"]), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
    )

    from src.services.notification_triggers import on_email_verified
    await on_email_verified(db, user["_id"])

    return {"message": "Email verified successfully. You can now log in."}


async def resend_verification(
    db: AsyncIOMotorDatabase, email: str, ip_address: str | None = None, user_agent_str: str | None = None
) -> dict:
    user = await _get_user_by_email(db, email)

    if user and user.get("is_active") and not user.get("is_email_verified"):
        now = datetime.now(timezone.utc)
        # Invalidate old tokens
        await db.email_verification_tokens.update_many(
            {"user_id": user["_id"], "used_at": None},
            {"$set": {"used_at": now}},
        )

        raw_token = generate_token()
        await db.email_verification_tokens.insert_one({
            "user_id": user["_id"],
            "token_hash": hash_token(raw_token),
            "expires_at": now + timedelta(hours=24),
            "used_at": None,
            "created_at": now,
        })

        await email_service.send_verification_email(email, raw_token)

    return {"message": "If an unverified account exists, a new verification email has been sent."}


# ── Login ────────────────────────────────────────────────────────────

async def login(
    db: AsyncIOMotorDatabase,
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

    if not user.get("is_active"):
        raise AuthenticationError("Account has been deactivated. Contact support.")

    now = datetime.now(timezone.utc)
    locked_until = user.get("locked_until")
    if locked_until:
        lock_time = locked_until.replace(tzinfo=timezone.utc) if locked_until.tzinfo is None else locked_until
        if lock_time > now:
            minutes_left = int((lock_time - now).total_seconds() / 60) + 1
            raise AccountLockedError(
                f"Account locked due to too many failed attempts. Try again in {minutes_left} minutes.",
                locked_until=lock_time.isoformat(),
            )
        else:
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"failed_login_count": 0, "locked_until": None}},
            )

    if not verify_password(password, user["password_hash"]):
        attempt = user.get("failed_login_count", 0) + 1

        await log_action(
            db, AuthAction.FAILED_LOGIN,
            user_id=str(user["_id"]), email=email,
            ip_address=ip_address, user_agent=user_agent_str,
            metadata={"attempt": attempt, "reason": "wrong_password"},
        )

        update_fields: dict = {"failed_login_count": attempt}

        if attempt >= 5:
            lock_until = now + timedelta(minutes=15)
            update_fields["locked_until"] = lock_until
            await db.users.update_one({"_id": user["_id"]}, {"$set": update_fields})
            await log_action(
                db, AuthAction.ACCOUNT_LOCKED,
                user_id=str(user["_id"]), email=email,
                ip_address=ip_address, user_agent=user_agent_str,
                metadata={"failed_attempts": attempt, "lockout_duration_minutes": 15},
            )
            raise AccountLockedError(
                "Account locked due to too many failed attempts. Try again in 15 minutes.",
                locked_until=lock_until.isoformat(),
            )

        await db.users.update_one({"_id": user["_id"]}, {"$set": update_fields})
        raise AuthenticationError("Invalid email or password")

    # Block unverified users
    if not user.get("is_email_verified"):
        raise AuthorizationError(
            "Please verify your email address before logging in. "
            "Check your inbox for the verification link."
        )

    # Success
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"failed_login_count": 0, "locked_until": None, "last_login_at": now}},
    )

    # Reload user for response (need agency data)
    user = await _reload_user(db, user["_id"])

    access, refresh = await _create_token_pair(db, user, ip_address, user_agent_str)

    await log_action(
        db, AuthAction.LOGIN,
        user_id=str(user["_id"]), email=email,
        ip_address=ip_address, user_agent=user_agent_str,
    )

    return _build_token_response(user, access, refresh)


# ── Token Refresh ────────────────────────────────────────────────────

async def refresh_tokens(
    db: AsyncIOMotorDatabase,
    refresh_token_str: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    payload = decode_token(refresh_token_str)
    if payload.get("type") != "refresh":
        raise AuthenticationError("Invalid token type")

    token_hash = hash_token(refresh_token_str)
    stored = await db.refresh_tokens.find_one({"token_hash": token_hash})

    if not stored:
        raise AuthenticationError("Invalid refresh token")
    if stored.get("revoked_at"):
        raise AuthenticationError("Token has been revoked")
    now = datetime.now(timezone.utc)
    expires = stored["expires_at"]
    if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        raise AuthenticationError("Refresh token has expired")

    user = await _reload_user(db, stored["user_id"])
    if not user or not user.get("is_active"):
        raise AuthenticationError("User not found or deactivated")

    # Rotate — revoke old token
    await db.refresh_tokens.update_one(
        {"_id": stored["_id"]}, {"$set": {"revoked_at": now}}
    )

    access, new_refresh = await _create_token_pair(db, user, ip_address, user_agent_str)

    await log_action(
        db, AuthAction.TOKEN_REFRESH,
        user_id=str(user["_id"]), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
    )

    return _build_token_response(user, access, new_refresh)


# ── Logout ───────────────────────────────────────────────────────────

async def logout(
    db: AsyncIOMotorDatabase,
    user: dict,
    refresh_token_str: str | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if refresh_token_str:
        token_hash = hash_token(refresh_token_str)
        await db.refresh_tokens.update_one(
            {"token_hash": token_hash, "user_id": user["_id"], "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(timezone.utc)}},
        )

    await log_action(
        db, AuthAction.LOGOUT,
        user_id=str(user["_id"]), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
    )

    return {"message": "Logged out successfully"}


# ── Invitation ───────────────────────────────────────────────────────

async def send_invitation(
    db: AsyncIOMotorDatabase,
    inviter: dict,
    email: str,
    role: str,
    agency_id: str | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    allowed_targets = INVITATION_PERMISSIONS.get(inviter["role"], [])
    if role not in allowed_targets:
        raise AuthorizationError(f"Role '{inviter['role']}' cannot invite '{role}' users")

    existing_user = await _get_user_by_email(db, email)
    if existing_user:
        raise ConflictError("A user with this email already exists")

    # Check for pending invitation
    now = datetime.now(timezone.utc)
    pending = await db.invitation_tokens.find_one({
        "email": email,
        "used_at": None,
        "expires_at": {"$gt": now},
    })
    if pending:
        raise ConflictError("An active invitation already exists for this email")

    resolved_agency_id = None
    agency_name = None

    if role == "agent":
        if not agency_id:
            raise ValidationError("agency_id is required when inviting an agent")
        try:
            agency_oid = ObjectId(agency_id)
        except Exception:
            raise NotFoundError("Agency not found")
        agency = await db.agencies.find_one({"_id": agency_oid})
        if not agency:
            raise NotFoundError("Agency not found")
        if not agency.get("is_active"):
            raise ValidationError("Agency has been deactivated")

        # Admins can invite agents to any agency; others must belong to the agency
        if inviter["role"] != "admin":
            is_member = await db.agencies.find_one({
                "_id": agency_oid,
                "members.user_id": inviter["_id"],
            })
            if not is_member:
                raise AuthorizationError("You can only invite agents to your own agency")

        resolved_agency_id = agency_oid
        agency_name = agency["name"]

    raw_token = generate_token()
    invitation_doc = {
        "token_hash": hash_token(raw_token),
        "email": email,
        "role": role,
        "invited_by": inviter["_id"],
        "agency_id": resolved_agency_id,
        "expires_at": now + timedelta(hours=24),
        "used_at": None,
        "created_at": now,
    }
    await db.invitation_tokens.insert_one(invitation_doc)

    # Get inviter name
    inviter_name = "Administrator"
    inviter_profile = inviter.get("profile")
    if inviter_profile:
        inviter_name = f"{inviter_profile.get('first_name', '')} {inviter_profile.get('last_name', '')}".strip()

    await email_service.send_invitation_email(email, raw_token, inviter_name, role, agency_name)

    await log_action(
        db, AuthAction.INVITATION_SENT,
        user_id=str(inviter["_id"]), email=inviter["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"invited_email": email, "role": role, "agency_id": str(resolved_agency_id) if resolved_agency_id else None},
    )

    return {
        "message": f"Invitation sent to {email}",
        "expires_at": invitation_doc["expires_at"].isoformat(),
    }


async def list_invitations(
    db: AsyncIOMotorDatabase,
    user: dict,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> dict:
    """List invitations created by the user."""
    now = datetime.now(timezone.utc)
    query: dict = {"invited_by": user["_id"]}

    if status == "pending":
        query["used_at"] = None
        query["expires_at"] = {"$gt": now}
    elif status == "used":
        query["used_at"] = {"$ne": None}
    elif status == "expired":
        query["used_at"] = None
        query["expires_at"] = {"$lte": now}

    total = await db.invitation_tokens.count_documents(query)

    cursor = db.invitation_tokens.find(query).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size)
    invitations = await cursor.to_list(length=page_size)

    items = []
    for inv in invitations:
        agency_name = None
        if inv.get("agency_id"):
            agency_doc = await db.agencies.find_one({"_id": inv["agency_id"]}, {"name": 1})
            if agency_doc:
                agency_name = agency_doc["name"]

        inv_status = "used" if inv.get("used_at") else ("expired" if inv["expires_at"] <= now else "pending")

        items.append({
            "id": str(inv["_id"]),
            "email": inv["email"],
            "role": inv["role"],
            "agency_name": agency_name,
            "status": inv_status,
            "expires_at": inv["expires_at"].isoformat(),
            "created_at": inv["created_at"].isoformat(),
            "used_at": inv["used_at"].isoformat() if inv.get("used_at") else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


async def validate_invitation(db: AsyncIOMotorDatabase, token: str) -> dict:
    token_hash = hash_token(token)
    invitation = await db.invitation_tokens.find_one({"token_hash": token_hash})

    if not invitation:
        raise ValidationError("Invalid invitation token")
    if invitation.get("used_at"):
        raise ValidationError("This invitation has already been used")
    if invitation["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValidationError("Invitation has expired. Please contact your administrator.")

    # Get inviter info
    inviter = await db.users.find_one({"_id": invitation["invited_by"]})
    inviter_info = {"name": "Unknown", "email": ""}
    if inviter:
        profile = inviter.get("profile")
        if profile:
            inviter_info = {
                "name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
                "email": inviter["email"],
            }

    agency_info = None
    if invitation.get("agency_id"):
        agency = await db.agencies.find_one({"_id": invitation["agency_id"]})
        if agency:
            agency_info = {"id": str(agency["_id"]), "name": agency["name"]}

    return {
        "email": invitation["email"],
        "role": invitation["role"],
        "invited_by": inviter_info,
        "agency": agency_info,
    }


async def signup_invited(
    db: AsyncIOMotorDatabase,
    token: str,
    password: str,
    first_name: str,
    last_name: str,
    phone: str | None = None,
    phone_number: str | None = None,
    address: dict | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    token_hash = hash_token(token)
    invitation = await db.invitation_tokens.find_one({"token_hash": token_hash})

    if not invitation:
        raise ValidationError("Invalid invitation token")
    if invitation.get("used_at"):
        raise ValidationError("This invitation has already been used")
    if invitation["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValidationError("Invitation has expired. Please contact your administrator.")

    violations = validate_password_strength(password)
    if violations:
        raise ValidationError("Password does not meet requirements", details=violations)

    existing = await _get_user_by_email(db, invitation["email"])
    if existing:
        raise ConflictError("A user with this email already exists")

    now = datetime.now(timezone.utc)
    user_doc = {
        "email": invitation["email"],
        "password_hash": hash_password(password),
        "role": invitation["role"],
        "is_email_verified": True,
        "is_active": True,
        "profile_completed": True,
        "profile": {
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "phone_number": phone_number,
            "company_name": None,
            "avatar_url": None,
            "metadata": {},
        },
        "phone_number": phone_number or phone,
        "address": address,
        "failed_login_count": 0,
        "locked_until": None,
        "last_login_at": None,
        "created_at": now,
        "updated_at": now,
    }
    insert_result = await db.users.insert_one(user_doc)
    user_id = insert_result.inserted_id

    # Add to agency if agent
    if invitation["role"] == "agent" and invitation.get("agency_id"):
        await db.agencies.update_one(
            {"_id": invitation["agency_id"]},
            {"$push": {"members": {
                "user_id": user_id,
                "role_in_agency": "agent",
                "joined_at": now,
            }}},
        )

    # Mark invitation used
    await db.invitation_tokens.update_one(
        {"_id": invitation["_id"]}, {"$set": {"used_at": now}}
    )

    # Reload user for response
    user = await _reload_user(db, user_id)

    access, refresh = await _create_token_pair(db, user, ip_address, user_agent_str)

    await log_action(
        db, AuthAction.INVITATION_USED,
        user_id=str(user_id), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"invited_by": str(invitation["invited_by"]), "role": invitation["role"]},
    )
    await log_action(
        db, AuthAction.SIGNUP,
        user_id=str(user_id), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"role": invitation["role"], "via": "invitation"},
    )

    return _build_token_response(user, access, refresh)


# ── Profile ──────────────────────────────────────────────────────────

async def complete_profile(
    db: AsyncIOMotorDatabase,
    user: dict,
    first_name: str,
    last_name: str,
    phone: str | None = None,
    phone_number: str | None = None,
    company_name: str | None = None,
    agency_id: str | None = None,
    address: dict | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if user.get("profile_completed"):
        raise ValidationError("Profile has already been completed")

    user_role = user["role"]
    if user_role == "importer" and not company_name:
        raise ValidationError("company_name is required for importers")

    if user_role in ("agency_manager", "agent"):
        if not agency_id:
            raise ValidationError("agency_id is required for agency managers and agents")
        try:
            agency_oid = ObjectId(agency_id)
        except Exception:
            raise NotFoundError("Agency not found")
        agency = await db.agencies.find_one({"_id": agency_oid})
        if not agency:
            raise NotFoundError("Agency not found")
        if not agency.get("is_active"):
            raise ValidationError("Agency has been deactivated")

    now = datetime.now(timezone.utc)
    profile_data = {
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "phone_number": phone_number,
        "company_name": company_name if user_role == "importer" else None,
        "avatar_url": None,
        "metadata": {},
    }

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "profile": profile_data,
            "profile_completed": True,
            "phone_number": phone_number or phone,
            "address": address,
            "updated_at": now,
        }},
    )

    if user_role in ("agency_manager", "agent") and agency_id:
        agency_oid = ObjectId(agency_id)
        role_in_agency = "manager" if user_role == "agency_manager" else "agent"
        await db.agencies.update_one(
            {"_id": agency_oid},
            {"$push": {"members": {
                "user_id": user["_id"],
                "role_in_agency": role_in_agency,
                "joined_at": now,
            }}},
        )

    user = await _reload_user(db, user["_id"])

    await log_action(
        db, AuthAction.PROFILE_UPDATED,
        user_id=str(user["_id"]), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"fields_set": ["first_name", "last_name", "phone", "company_name" if company_name else None]},
    )

    return {"message": "Profile completed successfully", "user": _build_user_response(user)}


async def get_profile(db: AsyncIOMotorDatabase, user: dict) -> dict:
    user = await _reload_user(db, user["_id"])
    return _build_user_response(user)


async def update_profile(
    db: AsyncIOMotorDatabase,
    user: dict,
    data: dict,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if not user.get("profile"):
        raise NotFoundError("Profile not found")

    changed = []
    update_fields = {}
    for field in ("first_name", "last_name", "phone", "phone_number", "company_name"):
        if field in data and data[field] is not None:
            update_fields[f"profile.{field}"] = data[field]
            changed.append(field)

    # Handle address as a nested object
    if "address" in data and data["address"] is not None:
        addr = data["address"]
        if isinstance(addr, dict):
            update_fields["address"] = addr
            changed.append("address")

    # Sync phone_number to top-level field
    if "phone_number" in data and data["phone_number"] is not None:
        update_fields["phone_number"] = data["phone_number"]

    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc)
        await db.users.update_one({"_id": user["_id"]}, {"$set": update_fields})

    user = await _reload_user(db, user["_id"])

    await log_action(
        db, AuthAction.PROFILE_UPDATED,
        user_id=str(user["_id"]), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"fields_changed": changed},
    )

    from src.services.notification_triggers import on_profile_updated
    await on_profile_updated(db, user["_id"])

    return {"message": "Profile updated", "user": _build_user_response(user)}


# ── Password Management ─────────────────────────────────────────────

async def forgot_password(
    db: AsyncIOMotorDatabase,
    email: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    user = await _get_user_by_email(db, email)

    if user and user.get("is_active") and user.get("is_email_verified"):
        now = datetime.now(timezone.utc)
        # Invalidate existing tokens
        await db.password_reset_tokens.update_many(
            {"user_id": user["_id"], "used_at": None},
            {"$set": {"used_at": now}},
        )

        raw_token = generate_token()
        await db.password_reset_tokens.insert_one({
            "user_id": user["_id"],
            "token_hash": hash_token(raw_token),
            "expires_at": now + timedelta(hours=1),
            "used_at": None,
            "created_at": now,
        })

        await email_service.send_password_reset_email(email, raw_token)

        await log_action(
            db, AuthAction.PASSWORD_RESET_REQUESTED,
            user_id=str(user["_id"]), email=email,
            ip_address=ip_address, user_agent=user_agent_str,
        )

    return {"message": "If an account exists with this email, a password reset link has been sent."}


async def reset_password(
    db: AsyncIOMotorDatabase,
    token: str,
    new_password: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    token_hash = hash_token(token)
    prt = await db.password_reset_tokens.find_one({"token_hash": token_hash})

    if not prt:
        raise ValidationError("Invalid or expired reset token")
    if prt.get("used_at"):
        raise ValidationError("Token has already been used")
    if prt["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValidationError("Reset token has expired. Please request a new one.")

    violations = validate_password_strength(new_password)
    if violations:
        raise ValidationError("Password does not meet requirements", details=violations)

    user = await db.users.find_one({"_id": prt["user_id"]})
    if not user or not user.get("is_active"):
        raise ValidationError("Account not found or deactivated")

    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "password_hash": hash_password(new_password),
            "failed_login_count": 0,
            "locked_until": None,
            "updated_at": now,
        }},
    )

    await db.password_reset_tokens.update_one(
        {"_id": prt["_id"]}, {"$set": {"used_at": now}}
    )

    # Revoke all refresh tokens
    revoke_result = await db.refresh_tokens.update_many(
        {"user_id": user["_id"], "revoked_at": None},
        {"$set": {"revoked_at": now}},
    )

    await log_action(
        db, AuthAction.PASSWORD_RESET,
        user_id=str(user["_id"]), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"sessions_revoked": revoke_result.modified_count},
    )

    return {"message": "Password has been reset successfully. Please log in with your new password."}


async def change_password(
    db: AsyncIOMotorDatabase,
    user: dict,
    current_password: str,
    new_password: str,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if not verify_password(current_password, user["password_hash"]):
        raise AuthenticationError("Current password is incorrect")

    if current_password == new_password:
        raise ValidationError("New password must be different from current password")

    violations = validate_password_strength(new_password)
    if violations:
        raise ValidationError("Password does not meet requirements", details=violations)

    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(new_password), "updated_at": now}},
    )

    # Revoke all refresh tokens
    revoke_result = await db.refresh_tokens.update_many(
        {"user_id": user["_id"], "revoked_at": None},
        {"$set": {"revoked_at": now}},
    )

    # Issue new tokens for current session
    user = await _reload_user(db, user["_id"])
    access, refresh = await _create_token_pair(db, user, ip_address, user_agent_str)

    await log_action(
        db, AuthAction.PASSWORD_CHANGED,
        user_id=str(user["_id"]), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"other_sessions_revoked": revoke_result.modified_count},
    )

    from src.services.notification_triggers import on_password_changed
    await on_password_changed(db, user["_id"])

    return {
        "message": "Password changed successfully. Other sessions have been logged out.",
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
    }
