# Step 01 — Project Setup & Configuration

> **Phase**: A (Foundation)  
> **Dependencies**: None (first step)  
> **Produces**: Runnable FastAPI skeleton, Docker environment, configuration system

---

## Objective

Create the `auth_services/` project skeleton — a FastAPI application that starts, connects to PostgreSQL, and serves a health check endpoint. Establish the configuration system, Docker setup, and project conventions that all subsequent steps build on.

---

## Files to Create

```
auth_services/
├── src/
│   ├── __init__.py
│   ├── main.py               # FastAPI app (CORS, health check, exception handlers)
│   └── config.py             # pydantic-settings configuration
├── requirements.txt           # 8 Python packages
├── Dockerfile                 # Multi-stage Python image
├── docker-compose.yml         # PostgreSQL + auth service
├── .env.example               # All required environment variables
└── .gitignore                 # Python standard ignores
```

---

## Configuration Variables (.env.example)

```env
# Application
APP_NAME=poruta-auth
APP_ENV=development
APP_PORT=5000
APP_DEBUG=true

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/poruta_auth

# JWT
JWT_SECRET_KEY=<generate-256-bit-secret>
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Email (Zoho SMTP)
SMTP_HOST=smtp.zoho.com
SMTP_PORT=587
SMTP_USERNAME=noreply@poruta.com
SMTP_PASSWORD=<zoho-app-password>
SMTP_FROM_EMAIL=noreply@poruta.com
SMTP_FROM_NAME=Poruta

# Frontend
FRONTEND_URL=http://localhost:3000

# Admin Seed (optional — auto-creates admin on first run)
ADMIN_EMAIL=
ADMIN_PASSWORD=

# CORS
CORS_ORIGINS=http://localhost:3000
```

---

## config.py Design

Use `pydantic-settings` to load all environment variables with type validation:

```python
class Settings(BaseSettings):
    # App
    app_name: str = "poruta-auth"
    app_env: str = "development"  # development | staging | production
    app_port: int = 5000
    app_debug: bool = True

    # Database
    database_url: str

    # JWT
    jwt_secret_key: str
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # SMTP
    smtp_host: str = "smtp.zoho.com"
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str
    smtp_from_email: str = "noreply@poruta.com"
    smtp_from_name: str = "Poruta"

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Admin seed
    admin_email: str | None = None
    admin_password: str | None = None

    # CORS
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)
```

---

## main.py Design

```python
# FastAPI app with:
# - CORS middleware (origins from config)
# - Lifespan handler (connect/disconnect DB, auto-seed admin)
# - Health check endpoint: GET /health → {"status": "healthy", "service": "poruta-auth"}
# - Global exception handlers for custom exceptions
# - Router inclusion (added in later steps)
```

---

## Docker Setup

### docker-compose.yml
- **`postgres`**: PostgreSQL 16, port 5432, volume for data persistence, creates `poruta_auth` database
- **`auth`**: Built from Dockerfile, port 5000, depends on postgres, env_file .env

### Dockerfile
- Multi-stage: `python:3.12-slim` base
- Install system deps for `asyncpg` and `argon2-cffi` (minimal: `libpq-dev`)
- Copy requirements, install, copy src
- Run with `uvicorn src.main:app --host 0.0.0.0 --port 5000`

---

## requirements.txt

```
fastapi==0.115.*
uvicorn[standard]==0.34.*
sqlalchemy[asyncio]==2.0.*
asyncpg==0.30.*
alembic==1.14.*
argon2-cffi==23.1.*
PyJWT==2.9.*
pydantic-settings==2.7.*
```

Pin to minor versions for reproducibility. Eight packages total.

---

## Acceptance Criteria

- [ ] `docker-compose up` starts PostgreSQL and the auth service
- [ ] `GET http://localhost:5000/health` returns `{"status": "healthy"}`
- [ ] Config loads all environment variables with defaults
- [ ] CORS allows requests from `CORS_ORIGINS`
- [ ] Invalid/missing required config variables cause startup failure with clear error message
- [ ] `.gitignore` prevents `.env`, `__pycache__`, `.pyc`, `alembic/versions/*.pyc` from being committed
