"""Password management API routes."""

from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.dependencies import get_current_user
from src.db.mongo import get_db
from src.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from src.services import auth_service
from src.services.log_service import get_client_ip

router = APIRouter(prefix="/password", tags=["password"])


@router.post("/forgot")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await auth_service.forgot_password(
        db,
        email=body.email,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/reset")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await auth_service.reset_password(
        db,
        token=body.token,
        new_password=body.new_password,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/change")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await auth_service.change_password(
        db,
        user=user,
        current_password=body.current_password,
        new_password=body.new_password,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )
