# Step 02 — Database Schema & Models

> **Phase**: A (Foundation)  
> **Dependencies**: Step 01 (project setup)  
> **Produces**: SQLAlchemy models, Alembic migration, Pydantic schemas

---

## Objective

Define all 9 database tables as SQLAlchemy async models, create PostgreSQL ENUMs for roles and audit actions, set up Alembic for migration management, and create the initial migration that builds the full schema.

---

## Files to Create

```
auth_services/
├── src/
│   ├── database.py               # Async engine, session factory, Base
│   ├── models/
│   │   ├── __init__.py            # Re-exports all models
│   │   ├── base.py                # Base class with UUID PK, timestamps
│   │   ├── user.py                # User, UserProfile
│   │   ├── agency.py              # Agency, UserAgency
│   │   ├── token.py               # RefreshToken, EmailVerificationToken, PasswordResetToken, InvitationToken
│   │   └── log.py                 # AuthLog
│   └── schemas/
│       ├── __init__.py
│       ├── auth.py                # SignupRequest, LoginRequest, TokenResponse, etc.
│       ├── user.py                # UserResponse, ProfileCompleteRequest, ProfileUpdateRequest
│       └── agency.py              # AgencyCreateRequest, AgencyResponse, AgencyUpdateRequest
├── alembic/
│   ├── env.py                     # Async Alembic config
│   ├── script.py.mako             # Migration template
│   └── versions/
│       └── 001_initial_schema.py  # Initial migration
└── alembic.ini
```

---

## PostgreSQL ENUMs

### UserRole
```
importer | agent | agency_manager | inspector | government | admin
```
Must match `poruta-front-end/src/types/roles.ts` exactly.

### AgencyRole
```
manager | agent
```
Used in `user_agency.role_in_agency`.

### AuthAction (16 values)
```
SIGNUP | LOGIN | LOGOUT | FAILED_LOGIN | EMAIL_VERIFY |
INVITATION_SENT | INVITATION_USED | PASSWORD_RESET |
PASSWORD_CHANGED | ACCOUNT_LOCKED | ACCOUNT_UNLOCKED |
PROFILE_UPDATED | ACCOUNT_DEACTIVATED | ACCOUNT_ACTIVATED |
TOKEN_REFRESH | ADMIN_CREATED | AGENCY_CREATED
```

---

## Table Specifications

### users
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, default uuid4 |
| email | VARCHAR(255) | UNIQUE, NOT NULL, indexed |
| password_hash | VARCHAR(255) | NOT NULL |
| role | UserRole ENUM | NOT NULL |
| is_email_verified | BOOLEAN | NOT NULL, default false |
| is_active | BOOLEAN | NOT NULL, default true |
| profile_completed | BOOLEAN | NOT NULL, default false |
| failed_login_count | INTEGER | NOT NULL, default 0 |
| locked_until | TIMESTAMP(tz) | NULLABLE |
| created_at | TIMESTAMP(tz) | NOT NULL, default now |
| updated_at | TIMESTAMP(tz) | NOT NULL, default now, onupdate now |
| last_login_at | TIMESTAMP(tz) | NULLABLE |

### user_profiles
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, UNIQUE, NOT NULL |
| first_name | VARCHAR(100) | NOT NULL |
| last_name | VARCHAR(100) | NO NULL |
| phone | VARCHAR(20) | NULLABLE |
| company_name | VARCHAR(255) | NULLABLE (required for importers) |
| avatar_url | VARCHAR(500) | NULLABLE |
| metadata | JSONB | NULLABLE, default {} |
| created_at | TIMESTAMP(tz) | NOT NULL |
| updated_at | TIMESTAMP(tz) | NOT NULL |

### agencies
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| name | VARCHAR(255) | NOT NULL |
| registration_number | VARCHAR(100) | UNIQUE, NOT NULL |
| address | TEXT | NULLABLE |
| phone | VARCHAR(20) | NULLABLE |
| email | VARCHAR(255) | NULLABLE |
| created_by | UUID | FK→users, NOT NULL |
| is_active | BOOLEAN | default true |
| created_at | TIMESTAMP(tz) | NOT NULL |
| updated_at | TIMESTAMP(tz) | NOT NULL |

### user_agency
| Column | Type | Constraints |
|--------|------|-------------|
| user_id | UUID | FK→users, PK (composite) |
| agency_id | UUID | FK→agencies, PK (composite) |
| role_in_agency | AgencyRole ENUM | NOT NULL |
| joined_at | TIMESTAMP(tz) | NOT NULL, default now |

### invitation_tokens
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| token_hash | VARCHAR(64) | UNIQUE, NOT NULL, indexed |
| email | VARCHAR(255) | NOT NULL |
| role | UserRole ENUM | NOT NULL |
| invited_by | UUID | FK→users, NOT NULL |
| agency_id | UUID | FK→agencies, NULLABLE |
| expires_at | TIMESTAMP(tz) | NOT NULL |
| used_at | TIMESTAMP(tz) | NULLABLE |
| created_at | TIMESTAMP(tz) | NOT NULL |

### email_verification_tokens
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, NOT NULL |
| token_hash | VARCHAR(64) | UNIQUE, NOT NULL, indexed |
| expires_at | TIMESTAMP(tz) | NOT NULL |
| used_at | TIMESTAMP(tz) | NULLABLE |
| created_at | TIMESTAMP(tz) | NOT NULL |

### password_reset_tokens
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, NOT NULL |
| token_hash | VARCHAR(64) | UNIQUE, NOT NULL, indexed |
| expires_at | TIMESTAMP(tz) | NOT NULL |
| used_at | TIMESTAMP(tz) | NULLABLE |
| created_at | TIMESTAMP(tz) | NOT NULL |

### refresh_tokens
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, NOT NULL |
| token_hash | VARCHAR(64) | UNIQUE, NOT NULL, indexed |
| device_info | VARCHAR(255) | NULLABLE |
| ip_address | VARCHAR(45) | NULLABLE (supports IPv6) |
| expires_at | TIMESTAMP(tz) | NOT NULL |
| revoked_at | TIMESTAMP(tz) | NULLABLE |
| created_at | TIMESTAMP(tz) | NOT NULL |

### auth_logs
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, NULLABLE (failed logins may not have a user) |
| action | AuthAction ENUM | NOT NULL, indexed |
| email | VARCHAR(255) | NULLABLE (for failed login attempts with unknown emails) |
| ip_address | VARCHAR(45) | NULLABLE |
| user_agent | TEXT | NULLABLE |
| metadata | JSONB | NULLABLE |
| created_at | TIMESTAMP(tz) | NOT NULL, indexed |

**Index**: composite index on `(created_at, action)` for log query performance.

---

## Base Model Class

```python
class BaseModel(DeclarativeBase):
    """All models inherit from this. Provides UUID PK and timestamps."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

---

## database.py Design

```python
# Async SQLAlchemy engine from config.database_url
# AsyncSessionLocal factory
# get_db() async generator for FastAPI dependency injection
# create_tables() function for development (Alembic for production)
```

---

## Pydantic Schemas (Key Types)

### auth.py
- `SignupRequest` — email, password, role (Literal["importer", "agency_manager"])
- `LoginRequest` — email, password
- `TokenResponse` — access_token, refresh_token, token_type, expires_in, user
- `RefreshRequest` — refresh_token
- `VerifyEmailRequest` — token
- `InvitedSignupRequest` — token, password, first_name, last_name, phone

### user.py
- `UserResponse` — id, email, role, is_email_verified, profile_completed, profile (nested)
- `ProfileCompleteRequest` — first_name, last_name, phone, company_name (optional), agency_id (optional)
- `ProfileUpdateRequest` — partial version of ProfileCompleteRequest
- `ProfileResponse` — first_name, last_name, phone, company_name, avatar_url, metadata

### agency.py
- `AgencyCreateRequest` — name, registration_number, address, phone, email
- `AgencyResponse` — id, name, registration_number, address, phone, email, is_active, created_at
- `AgencyUpdateRequest` — partial: name, address, phone, email

---

## Alembic Setup

### alembic.ini
- `sqlalchemy.url` read from environment (overridden in `env.py`)
- Async driver: `asyncpg`

### env.py
- Import all models so Alembic detects them for autogenerate
- Use `run_async_migrations()` pattern for async driver
- Target metadata from `BaseModel.metadata`

---

## Acceptance Criteria

- [ ] `alembic upgrade head` creates all 9 tables with correct columns and constraints
- [ ] `alembic downgrade base` drops all tables cleanly
- [ ] All foreign keys reference correct tables
- [ ] `token_hash` columns are indexed on all token tables
- [ ] `email` on users table has a unique constraint
- [ ] PostgreSQL ENUMs are created for UserRole, AgencyRole, AuthAction
- [ ] Pydantic schemas validate correctly (reject invalid emails, short passwords, unknown roles)
- [ ] `get_db()` provides async sessions to FastAPI route handlers
