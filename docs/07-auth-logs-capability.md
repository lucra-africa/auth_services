# Auth Logs & Audit Capability

## Overview

The Poruta authentication system maintains a comprehensive audit trail of every security-relevant action. Every signup, login, failed attempt, password change, invitation, and account modification is recorded with contextual metadata.

This document describes what gets logged, how admins can query it, and what security questions the log system answers.

---

## What Gets Logged

### 16 Tracked Actions

| Action | Trigger | Who's Recorded |
|--------|---------|----------------|
| `SIGNUP` | User creates account (self or invited) | New user |
| `LOGIN` | Successful login | Logged-in user |
| `LOGOUT` | User logs out | Logged-out user |
| `FAILED_LOGIN` | Wrong password or locked account | Attempted user (by email) |
| `EMAIL_VERIFY` | User verifies email | User |
| `INVITATION_SENT` | Manager/govt/admin sends invitation | Inviter |
| `INVITATION_USED` | Invited user completes signup | Invited user |
| `PASSWORD_RESET_REQUESTED` | User requests password reset email | User (if found) |
| `PASSWORD_RESET` | User successfully resets password | User |
| `PASSWORD_CHANGED` | User changes password while logged in | User |
| `ACCOUNT_LOCKED` | 5 failed login attempts | Locked user |
| `ACCOUNT_UNLOCKED` | Lockout expires or admin unlocks | User |
| `PROFILE_UPDATED` | User completes or updates profile | User |
| `ACCOUNT_DEACTIVATED` | Admin deactivates a user | Admin (as actor), target user in metadata |
| `ACCOUNT_ACTIVATED` | Admin reactivates a user | Admin (as actor), target user in metadata |
| `TOKEN_REFRESH` | Access token refreshed via refresh token | User |
| `ADMIN_CREATED` | Admin account created via CLI or auto-seed | Created admin |
| `AGENCY_CREATED` | Admin creates a new agency | Admin |

---

## Log Entry Structure

Each log entry contains:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique log entry identifier |
| `action` | ENUM | One of the 16 actions above |
| `user_id` | UUID (nullable) | The user performing or subject to the action |
| `email` | VARCHAR | Email associated with the action (for failed logins where user_id may be unknown) |
| `ip_address` | VARCHAR | Client IP address (handles X-Forwarded-For for reverse proxies) |
| `user_agent` | TEXT | Browser/client user-agent string |
| `metadata` | JSONB | Action-specific context (see below) |
| `created_at` | TIMESTAMP | When the action occurred |

---

## Metadata Examples

### FAILED_LOGIN
```json
{
  "attempt": 3,
  "reason": "wrong_password",
  "remaining_attempts": 2
}
```

### INVITATION_SENT
```json
{
  "invited_email": "agent@example.com",
  "role": "agent",
  "agency_id": "uuid",
  "agency_name": "Swift Customs Agency"
}
```

### ACCOUNT_DEACTIVATED
```json
{
  "target_user_id": "uuid",
  "target_email": "deactivated@example.com",
  "target_role": "agent",
  "reason": "Employee terminated"
}
```

### PASSWORD_RESET
```json
{
  "sessions_revoked": 3
}
```

### ADMIN_CREATED
```json
{
  "created_via": "cli",
  "email": "admin@poruta.io"
}
```

---

## Admin Query Interface

### Endpoint: GET /auth/logs

**Access**: System Admin only

### Available Filters

| Parameter | Type | Example | Description |
|-----------|------|---------|-------------|
| `action` | string | `FAILED_LOGIN` | Filter by action type |
| `user_id` | UUID | `550e8400-...` | Show all activity for one user |
| `email` | string | `@swiftcustoms` | Partial email match |
| `ip_address` | string | `41.186.30.52` | Filter by IP |
| `date_from` | ISO datetime | `2026-03-01T00:00:00Z` | Logs after this time |
| `date_to` | ISO datetime | `2026-03-08T23:59:59Z` | Logs before this time |
| `page` | int | `1` | Pagination |
| `page_size` | int | `50` | Results per page (max 200) |
| `sort_order` | string | `desc` | Sort by created_at |

### Example Queries

**"Show me all failed logins today"**
```
GET /auth/logs?action=FAILED_LOGIN&date_from=2026-03-08T00:00:00Z
```

**"Show all activity for a specific user"**
```
GET /auth/logs?user_id=550e8400-e29b-41d4-a716-446655440000
```

**"Show all admin actions"**
```
GET /auth/logs?action=ACCOUNT_DEACTIVATED&sort_order=desc
GET /auth/logs?action=AGENCY_CREATED&sort_order=desc
```

**"Is someone brute-forcing this email?"**
```
GET /auth/logs?email=target@example.com&action=FAILED_LOGIN
```

**"What happened from this IP address?"**
```
GET /auth/logs?ip_address=41.186.30.52
```

---

## Security Questions the Log Answers

| Question | How to Answer |
|----------|---------------|
| Is someone brute-forcing an account? | Filter FAILED_LOGIN by email, check frequency and IP patterns |
| Who invited this user? | Find INVITATION_USED for the user, check `invited_by` in metadata |
| When was the last successful login? | Filter LOGIN by user_id, sort desc, take first |
| Did the admin deactivate this account? | Filter ACCOUNT_DEACTIVATED by target_user_id in metadata |
| Was the password changed recently? | Filter PASSWORD_CHANGED or PASSWORD_RESET by user_id |
| How many users signed up this week? | Filter SIGNUP by date range, count |
| Which agencies were created today? | Filter AGENCY_CREATED by date_from=today |
| Is there suspicious activity from an IP? | Filter by ip_address, look for multiple FAILED_LOGIN from same IP |

---

## Data Retention

### v1 Policy
- All logs are retained indefinitely
- No automatic cleanup or archival
- The auth_logs table has indexes on `(created_at DESC, action)`, `(user_id)`, and `(action)` for query performance

### Future Considerations (not in v1)
- Automatic archival after 12 months (move to cold storage)
- Log export to CSV/JSON for compliance reporting
- Alert system for anomaly detection (e.g., >10 failed logins from same IP in 5 minutes)
- Monthly partitioning when table exceeds 10M rows

---

## Privacy Note

Auth logs contain PII (email, IP addresses). Access is restricted to admins only. The system does not expose logs via any public endpoint. In future, if GDPR/data-protection compliance is needed, a user data erasure process should be implemented for the logs table.
