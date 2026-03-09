"""Admin API routes: user management, log queries."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import require_role
from src.database import get_db
from src.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"])

require_admin = require_role("admin")


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
