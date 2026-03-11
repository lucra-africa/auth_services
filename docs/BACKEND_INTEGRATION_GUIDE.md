# Backend Integration Guide

How poruta-backend consumes auth_services for authentication, authorization, and user data.

## Architecture

```
poruta-front-end (port 9000)
     │
     ├── Auth requests ──→ auth_services (port 8050)
     │                        ↕ MongoDB (users, tokens, agencies)
     │
     └── Business requests ──→ poruta-backend (port 5000)
                                 ↕ PostgreSQL + MongoDB + Redis + MinIO
```

**auth_services** is the single source of truth for user identity. It issues RS256 JWT tokens that poruta-backend verifies using auth_services' public key.

---

## JWT Token Verification

### Algorithm: RS256 (asymmetric)

- **Private key**: Held only by auth_services (signs tokens)
- **Public key**: Shared with poruta-backend (verifies tokens)

### Setup

1. Copy `auth_services/keys/jwt-public.pem` to poruta-backend's config directory
2. In poruta-backend, load the public key and verify tokens:

```python
import jwt

public_key = open("keys/jwt-public.pem", "rb").read()
payload = jwt.decode(token, public_key, algorithms=["RS256"])
```

### Token Payload

```json
{
  "sub": "672f1a2b3c4d5e6f7a8b9c0d",
  "role": "government_rra",
  "backend_role": "STAKEHOLDER_RRA",
  "email": "officer@rra.gov.rw",
  "type": "access",
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "iat": 1710000000,
  "exp": 1710001800
}
```

| Claim | Description |
|-------|-------------|
| `sub` | User ID (MongoDB ObjectId string) |
| `role` | Auth-services role (lowercase) |
| `backend_role` | Maps directly to poruta-backend's `RoleEnum` |
| `email` | User's email address |
| `type` | `"access"` or `"refresh"` |
| `jti` | Unique token ID (for blacklisting) |

---

## Role Mapping

| Auth Role | Backend RoleEnum | Description |
|-----------|------------------|-------------|
| `importer` | `IMPORTER` | Submits customs declarations |
| `agent` | `AGENT` | Reviews documents, validates HS codes |
| `agency_manager` | `AGENCY_ADMIN` | Manages agency and agents |
| `inspector` | `STAKEHOLDER_WAREHOUSE` | Warehouse inspections |
| `government_rra` | `STAKEHOLDER_RRA` | Rwanda Revenue Authority |
| `government_rsb` | `STAKEHOLDER_RSB` | Rwanda Standards Board |
| `admin` | `SYSTEM_ADMIN` | Full system access |

Use the `backend_role` claim directly in `require_role()` checks — no mapping needed.

---

## Internal Service API

auth_services exposes internal endpoints for service-to-service user lookups.

### Authentication

All requests require the `X-Service-Key` header:

```
X-Service-Key: <value of SERVICE_API_KEY from auth_services .env>
```

### Endpoints

#### GET /api/v1/internal/users/{user_id}

Look up a single user.

**Response:**
```json
{
  "user_id": "672f1a2b3c4d5e6f7a8b9c0d",
  "email": "jean@example.com",
  "role": "importer",
  "backend_role": "IMPORTER",
  "first_name": "Jean",
  "last_name": "Mugisha",
  "phone_number": "250788001001",
  "address": {"street": "KG 11 Ave", "city": "Kigali", "province": null, "country": "Rwanda"},
  "agency_id": null,
  "is_active": true,
  "is_email_verified": true
}
```

#### POST /api/v1/internal/users/batch

Look up multiple users.

**Request:**
```json
{
  "user_ids": ["672f1a2b...", "672f1a2c..."]
}
```

**Response:** Array of user objects (same schema as single lookup). Max 100 per request.

#### GET /api/v1/internal/users/by-role/{role}

List users by role with pagination.

**Query params:** `page` (default 1), `page_size` (default 50, max 100)

**Response:**
```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 50
}
```

---

## Ports

| Service | Port | Purpose |
|---------|------|---------|
| auth_services | 8050 | Authentication, user management |
| poruta-backend | 5000 | Business logic, AI pipeline |
| poruta-front-end | 9000 | Next.js frontend |
| MongoDB (auth) | 27017 | Auth database |
| PostgreSQL (backend) | 5432 | Backend users/tasks |
