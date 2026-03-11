import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from src.config import settings

_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


# ── Role mapping to backend RoleEnum ─────────────────────────────────

ROLE_TO_BACKEND: dict[str, str] = {
    "importer": "IMPORTER",
    "agent": "AGENT",
    "agency_manager": "AGENCY_ADMIN",
    "inspector": "STAKEHOLDER_WAREHOUSE",
    "government_rra": "STAKEHOLDER_RRA",
    "government_rsb": "STAKEHOLDER_RSB",
    "admin": "SYSTEM_ADMIN",
}


# ── Password hashing ────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def validate_password_strength(password: str) -> list[str]:
    violations: list[str] = []
    if len(password) < 12:
        violations.append("Must be at least 12 characters")
    if not re.search(r"[A-Z]", password):
        violations.append("Must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        violations.append("Must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        violations.append("Must contain at least one digit")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>\[\]\\;'`~_+\-=/]", password):
        violations.append("Must contain at least one special character")
    return violations


# ── JWT key loading ──────────────────────────────────────────────────

_private_key_cache: bytes | None = None
_public_key_cache: bytes | None = None


def _load_private_key() -> bytes:
    global _private_key_cache
    if _private_key_cache is None:
        from pathlib import Path
        key_path = Path(settings.jwt_private_key_path)
        if not key_path.is_absolute():
            key_path = Path(__file__).resolve().parent.parent.parent / key_path
        _private_key_cache = key_path.read_bytes()
    return _private_key_cache


def _load_public_key() -> bytes:
    global _public_key_cache
    if _public_key_cache is None:
        from pathlib import Path
        key_path = Path(settings.jwt_public_key_path)
        if not key_path.is_absolute():
            key_path = Path(__file__).resolve().parent.parent.parent / key_path
        _public_key_cache = key_path.read_bytes()
    return _public_key_cache


def _get_signing_key_and_algorithm() -> tuple:
    """Return (key, algorithm) for signing JWT tokens."""
    if settings.jwt_private_key_path:
        return _load_private_key(), "RS256"
    return settings.jwt_secret_key, "HS256"


def _get_verification_key_and_algorithms() -> tuple:
    """Return (key, algorithms_list) for verifying JWT tokens."""
    if settings.jwt_public_key_path:
        return _load_public_key(), ["RS256"]
    return settings.jwt_secret_key, ["HS256"]


# ── JWT ──────────────────────────────────────────────────────────────

def create_access_token(user_id: str, role: str, email: str) -> str:
    key, algorithm = _get_signing_key_and_algorithm()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "backend_role": ROLE_TO_BACKEND.get(role, role.upper()),
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, key, algorithm=algorithm)


def create_refresh_token_jwt(user_id: str) -> str:
    key, algorithm = _get_signing_key_and_algorithm()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, key, algorithm=algorithm)


def create_shadow_token(
    target_user_id: str,
    target_role: str,
    target_email: str,
    admin_id: str,
    admin_email: str,
) -> str:
    """Create an access token for shadow mode with admin identity embedded."""
    key, algorithm = _get_signing_key_and_algorithm()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": target_user_id,
        "role": target_role,
        "backend_role": ROLE_TO_BACKEND.get(target_role, target_role.upper()),
        "email": target_email,
        "type": "access",
        "shadow_admin_id": admin_id,
        "shadow_admin_email": admin_email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, key, algorithm=algorithm)


def decode_token(token: str) -> dict:
    key, algorithms = _get_verification_key_and_algorithms()
    try:
        return jwt.decode(token, key, algorithms=algorithms)
    except jwt.ExpiredSignatureError:
        from src.core import AuthenticationError
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError:
        from src.core import AuthenticationError
        raise AuthenticationError("Invalid token")


# ── Token utilities ──────────────────────────────────────────────────

def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
