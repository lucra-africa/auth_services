from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import AuthenticationError, AuthorizationError
from src.core.security import decode_token
from src.database import get_db
from src.models.user import User


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
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

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthenticationError("Account has been deactivated")

    return user


def require_role(*roles: str):
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in roles:
            raise AuthorizationError(f"Role '{user.role.value}' is not authorized for this action")
        return user
    return _check


async def get_current_verified_user(
    user: User = Depends(get_current_user),
) -> User:
    if not user.is_email_verified:
        raise AuthorizationError("Email not verified")
    return user


async def get_current_complete_user(
    user: User = Depends(get_current_verified_user),
) -> User:
    if not user.profile_completed:
        raise AuthorizationError("Profile not completed")
    return user
