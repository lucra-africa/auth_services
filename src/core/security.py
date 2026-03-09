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


# ── JWT ──────────────────────────────────────────────────────────────

def create_access_token(user_id: str, role: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def create_refresh_token_jwt(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
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
