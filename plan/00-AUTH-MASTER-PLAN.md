# Poruta Authentication — Master Plan

> **Service**: `auth_services/` (standalone FastAPI microservice)  
> **Port**: 5000  
> **Database**: PostgreSQL (`poruta_auth` — separate from main `poruta` DB)  
> **Status**: Planning  

---

## Overview

Build a production authentication service for the Poruta customs clearance platform. Six user roles, each with distinct registration flows — from self-signup importers to invitation-only government officials. The system prioritizes auditability (every auth action is logged), security (Argon2id passwords, JWT tokens, invitation trust chains), and minimalism (8 Python packages total, zero third-party services beyond SMTP).

For detailed tradeoff analysis of every decision, see [TRADEOFF-ANALYSIS.md](./TRADEOFF-ANALYSIS.md).

---

## Roles & Registration Flows

| Role | How They Register | Invited By | Post-Registration |
|------|-------------------|------------|-------------------|
| **Importer** | Self-signup (`/signup`) | — | Verify email → Complete profile (name, phone, company) |
| **Agency Manager** | Self-signup (`/signup`) | — | Verify email → Complete profile → Associate with agency |
| **Custom Agent** | Invitation link (`/signup/invite?token=...`) | Agency Manager | Set password + profile → Auto-verified, auto-linked to agency |
| **Inspector** | Invitation link (`/signup/invite?token=...`) | Government/RRA / Admin | Set password + profile → Auto-verified |
| **Government/RRA** | Invitation link (`/signup/invite?token=...`) | System Admin | Set password + profile → Auto-verified |
| **System Admin** | CLI / env-var seed | System / Another Admin | Pre-created, no web signup |

> **Note:** System Admin can invite **any** role (importer, agent, agency_manager, inspector, government) via the invitation system.

---

## Security Posture

| Layer | Implementation |
|-------|---------------|
| Password hashing | Argon2id (OWASP #1 recommendation) |
| JWT signing | HS256 with 256-bit secret |
| Access token | 15-minute lifespan |
| Refresh token | 7-day lifespan, rotated on each refresh, DB-stored hash, revocable |
| Token storage | SHA-256 hashed (all token types — refresh, email verification, invitation, password reset) |
| Brute-force | 5 failed logins → 15-minute lockout per email |
| Password policy | 12+ characters, uppercase + lowercase + digit + special character |
| Invitation tokens | 24-hour expiry, single-use, cryptographically random |
| Admin creation | No web signup — CLI command or environment variable seed only |
| Email verification | Required for all self-signup users |
| Audit logging | Every auth action logged with IP, user-agent, timestamp, metadata |

---

## Database Schema (PostgreSQL — 9 tables)

```
┌──────────────────────┐     ┌──────────────────────────┐
│       users           │     │      user_profiles        │
│───────────────────────│     │──────────────────────────│
│ id (UUID PK)          │────▶│ user_id (FK)              │
│ email (unique)        │     │ first_name, last_name     │
│ password_hash         │     │ phone, company_name       │
│ role (enum)           │     │ avatar_url                │
│ is_email_verified     │     │ metadata (JSONB)          │
│ is_active             │     └──────────────────────────┘
│ profile_completed     │
│ failed_login_count    │     ┌──────────────────────────┐
│ locked_until          │     │       agencies            │
│ created_at            │     │──────────────────────────│
│ updated_at            │     │ id (UUID PK)              │
│ last_login_at         │     │ name                      │
└──────────────────────┘     │ registration_number       │
         │                    │ address, phone, email     │
         │                    │ created_by (FK→users)     │
         ▼                    │ is_active                 │
┌──────────────────────┐     └──────────────────────────┘
│    user_agency        │              │
│───────────────────────│              │
│ user_id (FK→users)    │◀─────────────┘
│ agency_id (FK→agency) │
│ role_in_agency (enum) │
│ joined_at             │
└──────────────────────┘

┌──────────────────────┐  ┌─────────────────────────────┐
│  invitation_tokens    │  │  email_verification_tokens   │
│───────────────────────│  │─────────────────────────────│
│ token_hash (SHA-256)  │  │ token_hash (SHA-256)         │
│ email, role           │  │ user_id (FK)                 │
│ invited_by (FK)       │  │ expires_at, used_at          │
│ agency_id (FK, null)  │  └─────────────────────────────┘
│ expires_at, used_at   │
└──────────────────────┘  ┌─────────────────────────────┐
                           │  password_reset_tokens       │
┌──────────────────────┐  │─────────────────────────────│
│   refresh_tokens      │  │ token_hash (SHA-256)         │
│───────────────────────│  │ user_id (FK)                 │
│ token_hash (SHA-256)  │  │ expires_at, used_at          │
│ user_id (FK)          │  └─────────────────────────────┘
│ device_info           │
│ ip_address            │  ┌─────────────────────────────┐
│ expires_at            │  │        auth_logs             │
│ revoked_at            │  │─────────────────────────────│
└──────────────────────┘  │ user_id (FK, nullable)       │
                           │ action (enum — 16 types)     │
                           │ email, ip_address            │
                           │ user_agent                   │
                           │ metadata (JSONB)             │
                           │ created_at                   │
                           └─────────────────────────────┘
```

---

## API Endpoints

### Auth Core
| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| POST | `/auth/signup` | Self-register (importer/agency_manager only) | No |
| POST | `/auth/verify-email` | Verify email with token | No |
| POST | `/auth/login` | Login, receive JWT tokens | No |
| POST | `/auth/refresh` | Rotate access + refresh tokens | Refresh token |
| POST | `/auth/logout` | Revoke refresh token | Access token |

### Invitation
| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| POST | `/auth/invite` | Send invitation (role-gated) | Yes (Manager/Gov/Admin) |
| GET | `/auth/invite/validate` | Validate invitation token | No |
| POST | `/auth/signup/invited` | Complete invited registration | No (token required) |

### Profile
| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| POST | `/auth/profile/complete` | Complete profile after signup | Yes |
| GET | `/auth/profile` | Get current user profile | Yes |
| PATCH | `/auth/profile` | Update profile fields | Yes |

### Password
| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| POST | `/auth/password/forgot` | Request password reset email | No |
| POST | `/auth/password/reset` | Reset password with token | No |
| POST | `/auth/password/change` | Change password (authenticated) | Yes |

### Agency Management
| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| POST | `/auth/agencies` | Create agency | Yes (Admin) |
| GET | `/auth/agencies` | List agencies | Yes (Admin/Manager) |
| GET | `/auth/agencies/{id}` | Agency detail | Yes (Admin/Manager) |
| PATCH | `/auth/agencies/{id}` | Update agency | Yes (Admin) |
| DELETE | `/auth/agencies/{id}` | Deactivate agency | Yes (Admin) |

### Admin
| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| GET | `/auth/users` | List users (paginated, filterable) | Yes (Admin) |
| PATCH | `/auth/users/{id}/deactivate` | Deactivate user | Yes (Admin) |
| PATCH | `/auth/users/{id}/activate` | Reactivate user | Yes (Admin) |
| POST | `/admin/shadow/{user_id}` | Start shadow session as target user | Yes (Admin) |
| POST | `/admin/shadow/end` | End shadow session | Yes (Admin) |

### Audit Logs
| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| GET | `/auth/logs` | Query audit logs (paginated, filterable) | Yes (Admin) |

---

## Implementation Phases

### Phase A: Foundation (Steps 1-3)
- **01** — Project setup, configuration, Docker
- **02** — Database schema, models, migrations
- **03** — Core security (Argon2id, JWT, token hashing, FastAPI dependencies)

### Phase B: Core Auth (Steps 4-6)
- **04** — Self-signup registration
- **05** — Email verification
- **06** — Login, token refresh, logout

### Phase C: Invitation & Profile (Steps 7-8)
- **07** — Invitation system (send, validate, complete)
- **08** — Profile completion (role-dependent)

### Phase D: Admin & Agency (Steps 9-10)
- **09** — Admin seeding (CLI + env-var)
- **10** — Agency CRUD (admin-managed)

### Phase E: Security & Logging (Steps 11-12)
- **11** — Password forgot/reset/change
- **12** — Audit logging system + admin query endpoint

### Phase F: Integration (Step 13)
- **13** — Frontend integration contract (API docs, auth flow diagrams, middleware strategy)

Each step has its own detailed plan file: `01-project-setup.md` through `13-frontend-integration.md`.

---

## Dependencies (8 Python packages)

```
fastapi              # Web framework
uvicorn[standard]    # ASGI server
sqlalchemy[asyncio]  # ORM + async support
asyncpg              # PostgreSQL async driver
alembic              # Database migrations
argon2-cffi          # Password hashing (Argon2id)
PyJWT                # JWT creation + verification (HS256)
pydantic-settings    # Environment variable configuration
```

No Redis, no Celery, no message queues, no third-party auth providers, no external APIs (besides your own Zoho SMTP). Email templates use Python f-strings (no Jinja2 dependency). Form data parsing uses JSON bodies (no python-multipart). SMTP uses stdlib `smtplib` via `asyncio.to_thread()` (no aiosmtplib).

---

## Project Structure

```
auth_services/
├── plan/                     # Feature plans
├── docs/                     # User stories + API reference
├── src/
│   ├── main.py               # FastAPI app entry point
│   ├── config.py             # pydantic-settings configuration
│   ├── database.py           # SQLAlchemy async engine + sessions
│   ├── models/               # ORM models (user, agency, token, log)
│   ├── schemas/              # Pydantic request/response schemas
│   ├── api/                  # FastAPI route handlers
│   ├── services/             # Business logic layer
│   ├── core/                 # Security, dependencies, exceptions
│   ├── templates/            # Email HTML templates (f-string based)
│   └── cli.py                # Admin CLI (create-admin command)
├── alembic/                  # Database migrations
├── tests/                    # pytest test suite
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── alembic.ini
```

---

## Cross-References

- **Tradeoff Analysis**: [plan/TRADEOFF-ANALYSIS.md](./TRADEOFF-ANALYSIS.md)
- **Feature Plans**: `plan/01-*.md` through `plan/13-*.md`
- **User Auth Stories**: `docs/01-*.md` through `docs/06-*.md`
- **Auth Logs Capability**: [docs/07-auth-logs-capability.md](../docs/07-auth-logs-capability.md)
- **API Reference**: [docs/AUTH_API_REFERENCE.md](../docs/AUTH_API_REFERENCE.md)
- **Frontend Roles**: `poruta-front-end/src/types/roles.ts` (must stay in sync)
- **Frontend Permissions**: `poruta-front-end/src/types/permissions.ts` (ROUTE_ACL)
