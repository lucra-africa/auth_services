"""Invitation API routes."""

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_verified_user
from src.database import get_db
from src.schemas.auth import InvitedSignupRequest, InviteRequest
from src.services import auth_service
from src.services.log_service import get_client_ip

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post("/create", status_code=201)
async def create_invitation(
    body: InviteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await auth_service.send_invitation(
        db,
        inviter=user,
        email=body.email,
        role=body.role,
        agency_id=body.agency_id,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/send", status_code=201)  # Kept for backward compatibility
async def send_invitation(
    body: InviteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await auth_service.send_invitation(
        db,
        inviter=user,
        email=body.email,
        role=body.role,
        agency_id=body.agency_id,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.get("/list")
async def list_invitations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(None, regex="^(pending|used|expired)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await auth_service.list_invitations(
        db, user=user, page=page, page_size=page_size, status=status
    )


@router.get("/validate/{token}")
async def validate_invitation(token: str, db: AsyncSession = Depends(get_db)):
    return await auth_service.validate_invitation(db, token=token)


@router.post("/signup")
async def invited_signup(
    body: InvitedSignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.signup_invited(
        db,
        token=body.token,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )
