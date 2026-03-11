"""Agency management API routes."""

from fastapi import APIRouter, Depends, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.dependencies import get_current_verified_user
from src.db.mongo import get_db
from src.schemas.agency import AgencyCreateRequest, AgencyUpdateRequest
from src.services import agency_service
from src.services.log_service import get_client_ip

router = APIRouter(prefix="/agencies", tags=["agencies"])


@router.post("", status_code=201)
async def create_agency(
    body: AgencyCreateRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await agency_service.create_agency(
        db,
        user=user,
        name=body.name,
        registration_number=body.registration_number,
        address=body.address,
        phone=body.phone,
        email=body.email,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )


@router.get("")
async def list_agencies(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await agency_service.list_agencies(
        db, user=user, page=page, page_size=page_size, search=search,
    )


@router.get("/{agency_id}")
async def get_agency(
    agency_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    return await agency_service.get_agency(db, user=user, agency_id=agency_id)


@router.patch("/{agency_id}")
async def update_agency(
    agency_id: str,
    body: AgencyUpdateRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_verified_user),
):
    data = body.model_dump(exclude_unset=True)
    return await agency_service.update_agency(
        db,
        user=user,
        agency_id=agency_id,
        data=data,
        ip_address=get_client_ip(request),
        user_agent_str=request.headers.get("user-agent"),
    )
