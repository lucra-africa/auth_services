"""Poruta Auth Service — FastAPI application."""

import logging
import time
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
from src.db.mongo import close_database, get_db, init_database
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

    db = get_db()
    await seed_admin(db)

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


# ── Request Logging Middleware ──────────────────────────────────────
# NOTE: Defined BEFORE CORSMiddleware so that Starlette's middleware
# stack puts CORS as the outermost layer.  This guarantees every
# response — including error 500s — carries CORS headers.

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing information."""
    start_time = time.time()
    
    client_host = request.client.host if request.client else "unknown"
    path = request.url.path
    method = request.method
    qs = f"?{request.query_params}" if request.query_params else ""

    # Detect shadow mode from JWT
    shadow_tag = ""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from src.core.security import decode_token
            payload = decode_token(auth_header[7:])
            admin_email = payload.get("shadow_admin_email")
            if admin_email:
                shadow_tag = f" [SHADOW by {admin_email}]"
        except Exception:
            pass

    logger.info("--> %s %s%s (from %s)%s", method, path, qs, client_host, shadow_tag)

    try:
        response = await call_next(request)
    except Exception:
        process_time = (time.time() - start_time) * 1000
        logger.exception("Unhandled error during %s %s [%.2fms]", method, path, process_time)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

    process_time = (time.time() - start_time) * 1000
    tag = "OK" if response.status_code < 400 else "FAIL"
    logger.info(
        "<-- %s %s %s [%s] %.2fms%s",
        tag, method, path, response.status_code, process_time, shadow_tag,
    )

    return response


# CORS — added AFTER @app.middleware so it wraps the logging middleware
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


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ── Health check ─────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "poruta-auth"}
