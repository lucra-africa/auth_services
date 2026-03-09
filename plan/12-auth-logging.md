# Step 12 — Auth Logging & Audit System

> **Phase**: E (Security & Logging)  
> **Dependencies**: Phase B (log_service already used by signup/login)  
> **Produces**: Log query endpoint, structured logging patterns

---

## Objective

Every authentication action produces a structured log entry in the `auth_logs` table. Admins can query, filter, and paginate these logs. This is the audit backbone — if something goes wrong (unauthorized access, suspicious patterns, compromised accounts), the auth log answers "who did what, when, from where."

---

## Actions Logged (16 total)

| Action | Logged By | Key Metadata |
|--------|-----------|-------------|
| `SIGNUP` | Step 04 | role, via (self/invitation) |
| `LOGIN` | Step 06 | — |
| `LOGOUT` | Step 06 | — |
| `FAILED_LOGIN` | Step 06 | attempt number, reason (wrong password/not found/locked) |
| `EMAIL_VERIFY` | Step 05 | — |
| `INVITATION_SENT` | Step 07 | invited_email, role, agency_id |
| `INVITATION_USED` | Step 07 | invitation_id, invited_by |
| `PASSWORD_RESET` | Step 11 | sessions_revoked count |
| `PASSWORD_CHANGED` | Step 11 | other_sessions_revoked count |
| `ACCOUNT_LOCKED` | Step 06 | failed_attempts, lockout_duration_minutes |
| `ACCOUNT_UNLOCKED` | Step 06 | via (auto_expire/admin_action) |
| `PROFILE_UPDATED` | Step 08 | fields changed |
| `ACCOUNT_DEACTIVATED` | Admin endpoint | deactivated_by admin user_id |
| `ACCOUNT_ACTIVATED` | Admin endpoint | activated_by admin user_id |
| `TOKEN_REFRESH` | Step 06 | — |
| `ADMIN_CREATED` | Step 09 | created_via (cli/auto_seed) |
| `AGENCY_CREATED` | Step 10 | agency_name, registration_number |

---

## Log Service (services/log_service.py)

### Core Function

```python
async def log_action(
    db: AsyncSession,
    action: AuthAction,
    user_id: uuid.UUID | None = None,
    email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None
) -> None:
    """Write a structured auth log entry.
    
    Never raises exceptions — logging failures should not break auth operations.
    If DB write fails, fall back to Python logger (stderr/file).
    """
```

### Usage Pattern

Every service function that performs an auth action calls `log_action()` as the final step within the same database transaction. If the main operation succeeds but logging fails, the operation still succeeds (logging is best-effort, not transactional with the main operation).

### Request Context Helper

```python
def get_request_context(request: Request) -> dict:
    """Extract IP address and user-agent from FastAPI request.
    Returns: {"ip_address": str, "user_agent": str}
    
    Handles X-Forwarded-For for reverse proxy scenarios.
    Priority: X-Forwarded-For → X-Real-IP → request.client.host
    """
```

---

## Admin Log Query Endpoint

### GET /auth/logs

**Auth**: `require_role("admin")`

#### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 50 | Items per page (max 200) |
| `action` | string | null | Filter by action type (e.g., "FAILED_LOGIN") |
| `user_id` | UUID | null | Filter by user |
| `email` | string | null | Filter by email (partial match) |
| `ip_address` | string | null | Filter by IP address |
| `date_from` | datetime | null | Logs after this timestamp |
| `date_to` | datetime | null | Logs before this timestamp |
| `sort_order` | string | "desc" | "asc" or "desc" by created_at |

#### Response (200)
```json
{
  "items": [
    {
      "id": "uuid",
      "action": "FAILED_LOGIN",
      "user_id": "uuid",
      "email": "user@example.com",
      "ip_address": "41.186.30.52",
      "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
      "metadata": {
        "attempt": 3,
        "reason": "wrong_password"
      },
      "created_at": "2026-03-08T14:22:10Z"
    },
    {
      "id": "uuid",
      "action": "LOGIN",
      "user_id": "uuid",
      "email": "admin@poruta.io",
      "ip_address": "41.186.30.52",
      "user_agent": "Mozilla/5.0...",
      "metadata": null,
      "created_at": "2026-03-08T14:20:05Z"
    }
  ],
  "total": 1523,
  "page": 1,
  "page_size": 50,
  "total_pages": 31
}
```

---

## Query Performance

The `auth_logs` table will grow continuously. To keep queries fast:

1. **Composite index**: `(created_at DESC, action)` — most queries filter by time range and action type
2. **Index on user_id**: For "show all activity for this user" queries
3. **Index on action**: For "show all failed logins" queries
4. **No table partitioning initially**: Implement monthly partitioning when the table exceeds ~10M rows. For a system with hundreds of users, this threshold is years away.

---

## What the Log Answers

| Question | Filter |
|----------|--------|
| "Who logged in last night?" | action=LOGIN, date_from=last_night |
| "How many failed logins today?" | action=FAILED_LOGIN, date_from=today |
| "Who invited this agent?" | action=INVITATION_USED, user_id=agent_id |
| "Was this admin account created via CLI?" | action=ADMIN_CREATED |
| "Is someone brute-forcing this account?" | email=X, action=FAILED_LOGIN, sort by created_at |
| "Who deactivated this user?" | action=ACCOUNT_DEACTIVATED, metadata→deactivated_user_id |
| "What changes did this admin make?" | user_id=admin_id, sort by created_at |

---

## User Activity Summary (Future Enhancement)

Not in v1, but prepared for:

```python
# GET /auth/users/{id}/activity — admin endpoint
# Returns last_login, signup_date, login_count, failed_login_count, password_changed_at
# Computed from auth_logs aggregation
```

The schema supports this without changes — it's a query against existing data.

---

## Acceptance Criteria

- [ ] Every auth action listed above produces a log entry
- [ ] Log entries include user_id, email, ip_address, user_agent, metadata
- [ ] Log writes never crash the parent operation (best-effort)
- [ ] GET /auth/logs returns paginated results (admin only)
- [ ] Filtering by action, user_id, email, date range all work
- [ ] Non-admin users receive 403 on GET /auth/logs
- [ ] IP address extraction handles X-Forwarded-For header
- [ ] Composite index on (created_at, action) exists
- [ ] JSONB metadata contains contextual details for each action type
