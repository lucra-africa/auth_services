# Poruta Auth Service — API Reference

> **Base URL**: `http://localhost:5000` (dev) / `https://auth.poruta.com` (prod)  
> **Content-Type**: `application/json` (all requests and responses)  
> **Authentication**: Bearer token in `Authorization` header (where required)

---

## Error Response Format

All error responses follow this structure:
```json
{
  "error": "error_type",
  "message": "Human-readable description",
  "details": null | ["specific", "issues"]
}
```

---

## Authentication Endpoints

### POST /auth/signup

Self-registration for importers and agency managers.

| | |
|---|---|
| **Auth** | None |
| **Rate Limit** | 5 requests per 15 minutes per IP |

**Request:**
```json
{
  "email": "user@example.com",
  "password": "Str0ng!P@ssw0rd",
  "role": "importer"
}
```

| Field | Type | Rules |
|-------|------|-------|
| `email` | string | Required, valid email, unique |
| `password` | string | Required, 12+ chars, upper+lower+digit+special |
| `role` | string | Required, one of: `importer`, `agency_manager` |

**Response (201):**
```json
{
  "message": "Account created. Please check your email to verify your account.",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "importer",
    "is_email_verified": false,
    "profile_completed": false
  }
}
```

| Error | Code |
|-------|------|
| Email already registered | 409 |
| Invalid role (not importer/agency_manager) | 422 |
| Weak password | 422 (details: list of violations) |

---

### POST /auth/verify-email

**Auth:** None

**Request:**
```json
{
  "token": "urlsafe-base64-token"
}
```

**Response (200):**
```json
{
  "message": "Email verified successfully. You can now log in."
}
```

| Error | Code |
|-------|------|
| Invalid/expired/used token | 400 |

---

### POST /auth/verify-email/resend

**Auth:** None

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response (200 — always):**
```json
{
  "message": "If an unverified account exists, a new verification email has been sent."
}
```

---

### POST /auth/login

**Auth:** None  
**Rate Limit:** 5 failed attempts → 15-minute lockout

**Request:**
```json
{
  "email": "user@example.com",
  "password": "Str0ng!P@ssw0rd"
}
```

**Response (200):**
```json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "importer",
    "is_email_verified": true,
    "profile_completed": true,
    "profile": {
      "first_name": "Jean-Pierre",
      "last_name": "Habimana",
      "phone": "+250788123456",
      "company_name": "Kigali Electronics Ltd",
      "avatar_url": null
    }
  }
}
```

**Set-Cookie header (refresh token):**
```
Set-Cookie: poruta_refresh_token=eyJ...; HttpOnly; Secure; SameSite=Strict; Path=/auth/refresh; Max-Age=604800
```

| Error | Code |
|-------|------|
| Invalid credentials | 401 |
| Email not verified | 403 |
| Account deactivated | 403 |
| Account locked | 423 (message includes unlock time) |

---

### POST /auth/refresh

**Auth:** Refresh token cookie (sent automatically by browser)

**Request:** Empty body. Token from `poruta_refresh_token` cookie.

**Response (200):**
```json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": { ... }
}
```

New refresh token set via `Set-Cookie` (token rotation).

| Error | Code |
|-------|------|
| Missing/invalid/expired/revoked token | 401 |

---

### POST /auth/logout

**Auth:** Bearer token

**Request:** Empty body.

**Response (200):**
```json
{
  "message": "Logged out successfully"
}
```

Clears refresh token cookie (`Max-Age=0`) and revokes the refresh token in the database.

---

## Invitation Endpoints

### POST /auth/invite

**Auth:** Bearer token (agency_manager, government, or admin)

**Request:**
```json
{
  "email": "invitee@example.com",
  "role": "agent",
  "agency_id": "uuid"
}
```

| Field | Type | Rules |
|-------|------|-------|
| `email` | string | Required, valid email |
| `role` | string | Required, must be an allowed target for inviter's role |
| `agency_id` | UUID | Required when role=agent, ignored otherwise |

**Permission Matrix:**

| Inviter | Can Invite |
|---------|-----------|
| agency_manager | agent |
| government | inspector |
| admin | government |

**Response (201):**
```json
{
  "message": "Invitation sent to invitee@example.com",
  "expires_at": "2026-03-09T14:30:00Z"
}
```

| Error | Code |
|-------|------|
| Unauthorized role combination | 403 |
| Email already registered | 409 |
| Pending invitation exists | 409 |
| Agency not found (for agent invite) | 404 |
| Missing agency_id for agent role | 422 |

---

### GET /auth/invite/validate

**Auth:** None

**Query:** `?token=urlsafe-base64-token`

**Response (200):**
```json
{
  "email": "invitee@example.com",
  "role": "agent",
  "invited_by": {
    "name": "Patrick Ndayisaba",
    "email": "p.ndayisaba@swiftcustoms.rw"
  },
  "agency": {
    "id": "uuid",
    "name": "Swift Customs Agency"
  }
}
```

| Error | Code |
|-------|------|
| Invalid/expired/used token | 400 |

---

### POST /auth/signup/invited

**Auth:** None (token-authenticated)

**Request:**
```json
{
  "token": "urlsafe-base64-token",
  "password": "Str0ng!P@ssw0rd",
  "first_name": "Marie-Claire",
  "last_name": "Uwimana",
  "phone": "+250788654321"
}
```

**Response (201):** Same structure as login response (auto-login).

| Error | Code |
|-------|------|
| Invalid/expired/used token | 400 |
| Weak password | 422 |
| Email already registered (race condition) | 409 |

---

## Profile Endpoints

### POST /auth/profile/complete

**Auth:** Bearer token (email verified, profile incomplete)

**Request:**
```json
{
  "first_name": "Jean-Pierre",
  "last_name": "Habimana",
  "phone": "+250788123456",
  "company_name": "Kigali Electronics Ltd",
  "agency_id": null
}
```

| Field | Required For |
|-------|-------------|
| `first_name` | All |
| `last_name` | All |
| `phone` | All |
| `company_name` | Importers only |
| `agency_id` | Agency Managers only |

**Response (200):**
```json
{
  "message": "Profile completed successfully",
  "user": { ... }
}
```

| Error | Code |
|-------|------|
| Profile already completed | 400 |
| Email not verified | 403 |
| Missing required role-specific field | 422 |
| Agency not found | 404 |

---

### GET /auth/profile

**Auth:** Bearer token

**Response (200):**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "role": "importer",
  "is_email_verified": true,
  "profile_completed": true,
  "profile": {
    "first_name": "Jean-Pierre",
    "last_name": "Habimana",
    "phone": "+250788123456",
    "company_name": "Kigali Electronics Ltd",
    "avatar_url": null,
    "metadata": {}
  },
  "agency": null
}
```

---

### PATCH /auth/profile

**Auth:** Bearer token (profile must be completed)

**Request (partial):**
```json
{
  "phone": "+250788999888"
}
```

Updatable: `first_name`, `last_name`, `phone`, `company_name`, `metadata`

**Response (200):** Updated profile object.

---

## Password Endpoints

### POST /auth/password/forgot

**Auth:** None

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response (200 — always):**
```json
{
  "message": "If an account exists with this email, a password reset link has been sent."
}
```

---

### POST /auth/password/reset

**Auth:** None (token-authenticated)

**Request:**
```json
{
  "token": "urlsafe-base64-token",
  "new_password": "N3w!Str0ngP@ss"
}
```

**Response (200):**
```json
{
  "message": "Password has been reset successfully. Please log in with your new password."
}
```

Revokes all sessions. Clears account lockout.

| Error | Code |
|-------|------|
| Invalid/expired/used token | 400 |
| Weak password | 422 |

---

### POST /auth/password/change

**Auth:** Bearer token

**Request:**
```json
{
  "current_password": "OldP@ssw0rd123",
  "new_password": "N3w!Str0ngP@ss"
}
```

**Response (200):**
```json
{
  "message": "Password changed successfully. Other sessions have been logged out."
}
```

| Error | Code |
|-------|------|
| Wrong current password | 401 |
| Same as current password | 422 |
| Weak new password | 422 |

---

## Agency Endpoints

### POST /auth/agencies

**Auth:** Admin only

**Request:**
```json
{
  "name": "Swift Customs Agency",
  "registration_number": "RCA-2024-00456",
  "address": "KN 5 Rd, Kigali",
  "phone": "+250788555444",
  "email": "info@swiftcustoms.rw"
}
```

**Response (201):** Created agency object.

| Error | Code |
|-------|------|
| Duplicate registration number | 409 |
| Not admin | 403 |

---

### GET /auth/agencies

**Auth:** Admin or Agency Manager

**Query:** `?page=1&page_size=20&search=swift&is_active=true`

**Response (200):**
```json
{
  "items": [...],
  "total": 12,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### GET /auth/agencies/{id}

**Auth:** Admin (any agency) or Agency Manager (own agency only)

**Response (200):** Full agency object with members list.

---

### PATCH /auth/agencies/{id}

**Auth:** Admin only

**Request (partial):**
```json
{
  "name": "Updated Name"
}
```

**Response (200):** Updated agency object.

---

### DELETE /auth/agencies/{id}

**Auth:** Admin only. Soft-deactivates (sets `is_active=false`).

**Response (200):**
```json
{
  "message": "Agency deactivated",
  "id": "uuid",
  "name": "Agency Name"
}
```

---

## Admin Endpoints

### GET /auth/users

**Auth:** Admin only

**Query:** `?page=1&page_size=20&role=agent&search=marie&is_active=true`

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "role": "agent",
      "is_active": true,
      "is_email_verified": true,
      "profile_completed": true,
      "profile": { ... },
      "agency": { ... },
      "created_at": "...",
      "last_login_at": "..."
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

---

### PATCH /auth/users/{id}/deactivate

**Auth:** Admin only. Cannot deactivate other admins.

**Response (200):**
```json
{
  "message": "User deactivated",
  "user_id": "uuid"
}
```

Revokes all user's active sessions.

---

### PATCH /auth/users/{id}/activate

**Auth:** Admin only.

**Response (200):**
```json
{
  "message": "User activated",
  "user_id": "uuid"
}
```

---

### GET /auth/logs

**Auth:** Admin only

**Query:** `?action=FAILED_LOGIN&user_id=uuid&email=@example&ip_address=41.186.30.52&date_from=2026-03-01&date_to=2026-03-08&page=1&page_size=50&sort_order=desc`

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "action": "FAILED_LOGIN",
      "user_id": "uuid",
      "email": "user@example.com",
      "ip_address": "41.186.30.52",
      "user_agent": "Mozilla/5.0...",
      "metadata": {"attempt": 3, "reason": "wrong_password"},
      "created_at": "2026-03-08T14:22:10Z"
    }
  ],
  "total": 1523,
  "page": 1,
  "page_size": 50,
  "total_pages": 31
}
```

---

## Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad request (invalid token, already completed, etc.) |
| 401 | Unauthorized (missing/invalid access token, wrong password) |
| 403 | Forbidden (insufficient role, email not verified) |
| 404 | Not found |
| 409 | Conflict (duplicate email, duplicate invitation) |
| 422 | Validation error (weak password, missing required fields) |
| 423 | Locked (account locked due to failed attempts) |
| 429 | Rate limited |
| 500 | Internal server error |

---

## Token Specification

| Token | Algorithm | Lifetime | Storage | Transport |
|-------|-----------|----------|---------|-----------|
| Access | HS256 (PyJWT) | 15 min | Client memory | `Authorization: Bearer` header |
| Refresh | Random (secrets.token_urlsafe) | 7 days | DB (SHA-256 hash) | httpOnly cookie |
| Email Verification | Random (secrets.token_urlsafe) | 24 hours | DB (SHA-256 hash) | Email URL |
| Password Reset | Random (secrets.token_urlsafe) | 1 hour | DB (SHA-256 hash) | Email URL |
| Invitation | Random (secrets.token_urlsafe) | 24 hours | DB (SHA-256 hash) | Email URL |

### Access Token JWT Payload
```json
{
  "sub": "user-uuid",
  "role": "importer",
  "iat": 1709900000,
  "exp": 1709900900
}
```
