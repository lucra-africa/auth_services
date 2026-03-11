"""Auth API routes: signup, login, verify, refresh, logout."""

from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.dependencies import get_current_user
from src.db.mongo import get_db
from src.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    ResendVerificationRequest,
    SignupRequest,
    VerifyEmailRequest,
)
from src.services import auth_service
from src.services.log_service import get_client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", status_code=201)
async def signup(body: SignupRequest, request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await auth_service.signup(
        db,
        email=body.email,
        password=body.password,
        role=body.role,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/login")
async def login(body: LoginRequest, request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await auth_service.login(
        db,
        email=body.email,
        password=body.password,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await auth_service.verify_email(
        db,
        token=body.token,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/resend-verification")
async def resend_verification(body: ResendVerificationRequest, request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await auth_service.resend_verification(
        db,
        email=body.email,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await auth_service.refresh_tokens(
        db,
        refresh_token_str=body.refresh_token,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/logout")
async def logout(request: Request, db: AsyncIOMotorDatabase = Depends(get_db), user=Depends(get_current_user)):
    body = await request.json()
    refresh_token = body.get("refresh_token")
    return await auth_service.logout(
        db,
        user=user,
        refresh_token_str=refresh_token,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )
