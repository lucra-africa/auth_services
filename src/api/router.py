"""API route aggregation."""

from fastapi import APIRouter

from src.api.admin import router as admin_router
from src.api.agencies import router as agencies_router
from src.api.auth import router as auth_router
from src.api.invitations import router as invitations_router
from src.api.messaging import router as messaging_router
from src.api.notifications import router as notifications_router
from src.api.password import router as password_router
from src.api.profile import router as profile_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(invitations_router)
api_router.include_router(profile_router)
api_router.include_router(password_router)
api_router.include_router(agencies_router)
api_router.include_router(admin_router)
api_router.include_router(messaging_router)
api_router.include_router(notifications_router)
