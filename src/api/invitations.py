"""Invitation API routes."""

from fastapi import APIRouter, Depends, Request, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.dependencies import get_current_verified_user
from src.db.mongo import get_db
from src.schemas.auth import BulkInviteRequest, InvitedSignupRequest, InviteRequest
from src.services import auth_service
from src.services.log_service import get_client_ip

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post("/create", status_code=201)
async def create_invitation(
    body: InviteRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
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
    db: AsyncIOMotorDatabase = Depends(get_db),
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


@router.post("/bulk", status_code=201)
async def bulk_send_invitations(
    body: BulkInviteRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await auth_service.bulk_send_invitations(
        db,
        inviter=user,
        invitations_list=[inv.model_dump() for inv in body.invitations],
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.get("/stats")
async def get_invitation_stats(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await auth_service.get_invitation_stats(db, user=user)


@router.get("/list")
async def list_invitations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(None, pattern="^(pending|used|expired|revoked)$"),
    search: str = Query(None, min_length=1, max_length=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await auth_service.list_invitations(
        db, user=user, page=page, page_size=page_size, status=status, search=search,
    )


@router.post("/{invitation_id}/revoke")
async def revoke_invitation(
    invitation_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await auth_service.revoke_invitation(
        db,
        invitation_id=invitation_id,
        revoker=user,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await auth_service.resend_invitation(
        db,
        invitation_id=invitation_id,
        resender=user,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.get("/validate/{token}")
async def validate_invitation(token: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await auth_service.validate_invitation(db, token=token)


@router.post("/signup")
async def invited_signup(
    body: InvitedSignupRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await auth_service.signup_invited(
        db,
        token=body.token,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        phone_number=body.phone_number,
        address=body.address.model_dump() if body.address else None,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )
