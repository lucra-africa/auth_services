"""Admin API routes: user management, log queries, shadow mode."""

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import require_role
from src.database import get_db
from src.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"])

require_admin = require_role("admin")


class EndShadowRequest(BaseModel):
    shadowed_user_id: str


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: str | None = Query(None),
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    return await admin_service.list_users(
        db, page=page, page_size=page_size, role=role, search=search, is_active=is_active,
    )


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    return await admin_service.get_user(db, user_id=user_id)


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    return await admin_service.deactivate_user(db, admin=admin, user_id=user_id)


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    return await admin_service.activate_user(db, admin=admin, user_id=user_id)


@router.get("/logs")
async def get_auth_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: str | None = Query(None),
    action: str | None = Query(None),
    email: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    return await admin_service.get_auth_logs(
        db, page=page, page_size=page_size, user_id=user_id, action=action, email=email,
    )


@router.post("/shadow/end")
async def end_shadow(
    body: EndShadowRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    """Log the end of a shadow session."""
    return await admin_service.end_shadow(
        db,
        admin=admin,
        shadowed_user_id=body.shadowed_user_id,
        ip_address=request.client.host if request.client else None,
        user_agent_str=request.headers.get("user-agent"),
    )


@router.post("/shadow/{user_id}")
async def shadow_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    """Start a shadow session — admin receives a token that acts as the target user."""
    return await admin_service.shadow_user(
        db,
        admin=admin,
        user_id=user_id,
        ip_address=request.client.host if request.client else None,
        user_agent_str=request.headers.get("user-agent"),
    )
