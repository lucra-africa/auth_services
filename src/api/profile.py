"""Profile API routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_current_verified_user
from src.database import get_db
from src.schemas.user import ProfileCompleteRequest, ProfileUpdateRequest
from src.services import auth_service
from src.services.log_service import get_client_ip

router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/complete")
async def complete_profile(
    body: ProfileCompleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await auth_service.complete_profile(
        db,
        user=user,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        company_name=body.company_name,
        agency_id=body.agency_id,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.get("/me")
async def get_profile(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await auth_service.get_profile(db, user=user)


@router.patch("/me")
async def update_profile(
    body: ProfileUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    data = body.model_dump(exclude_unset=True)
    return await auth_service.update_profile(
        db,
        user=user,
        data=data,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )
