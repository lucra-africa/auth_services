from bson import ObjectId
from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core import AuthenticationError, AuthorizationError
from src.core.security import decode_token
from src.db.mongo import get_db


async def get_current_user(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header")

    token = auth_header[7:]
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise AuthenticationError("Invalid token payload")

    user = await db.users.find_one({"_id": oid})

    if not user:
        raise AuthenticationError("User not found")
    if not user.get("is_active"):
        raise AuthenticationError("Account has been deactivated")

    return user


def require_role(*roles: str):
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise AuthorizationError(f"Role '{user['role']}' is not authorized for this action")
        return user
    return _check


async def get_current_verified_user(
    user: dict = Depends(get_current_user),
) -> dict:
    if not user.get("is_email_verified"):
        raise AuthorizationError("Email not verified")
    return user


async def get_current_complete_user(
    user: dict = Depends(get_current_verified_user),
) -> dict:
    if not user.get("profile_completed"):
        raise AuthorizationError("Profile not completed")
    return user
