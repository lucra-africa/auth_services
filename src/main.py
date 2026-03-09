"""Poruta Auth Service — FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import settings
from src.core import (
    AccountLockedError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from src.database import close_database, get_db, init_database
from src.api.router import api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Poruta Auth Service")
    await init_database()

    # Auto-seed admin
    from src.services.admin_service import seed_admin

    async for db in get_db():
        await seed_admin(db)
        await db.commit()
        break

    logger.info("Auth service ready on port %s", settings.app_port)
    yield
    await close_database()
    logger.info("Auth service shut down")


app = FastAPI(
    title="Poruta Auth Service",
    version="1.0.0",
    description="Authentication and authorization service for Poruta customs clearance platform",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Routes
app.include_router(api_router)


# ── Exception handlers ──────────────────────────────────────────────

@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(status_code=401, content={"error": exc.message})


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError):
    return JSONResponse(status_code=403, content={"error": exc.message})


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    body = {"error": exc.message}
    if exc.details:
        body["details"] = exc.details
    return JSONResponse(status_code=422, content=body)


@app.exception_handler(ConflictError)
async def conflict_error_handler(request: Request, exc: ConflictError):
    return JSONResponse(status_code=409, content={"error": exc.message})


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"error": exc.message})


@app.exception_handler(AccountLockedError)
async def account_locked_error_handler(request: Request, exc: AccountLockedError):
    return JSONResponse(
        status_code=423,
        content={"error": exc.message, "locked_until": exc.locked_until},
    )


# ── Health check ─────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "poruta-auth"}
