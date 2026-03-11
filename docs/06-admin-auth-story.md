# System Admin Authentication Story

## Who is the System Admin?

The System Admin is the root user of the Poruta platform. They bootstrap the entire organizational structure: creating agencies, inviting government officials, and managing all user accounts. Admin accounts are never created through the web interface — they are provisioned via CLI or auto-seeded on first startup.

---

## Account Creation

### There is no admin signup page.

Admins are created through one of two methods:

### Method 1: CLI Command (Recommended for Production)

A system administrator with server access runs:
```bash
python -m src.cli create-admin \
  --email admin@poruta.io \
  --password "Str0ng!Adm1n#Pass" \
  --first-name System \
  --last-name Administrator
```

The CLI:
1. Validates password strength (same 12+ char policy)
2. Checks email isn't already registered
3. Creates admin account (email verified, profile complete)
4. Outputs confirmation

### Method 2: Auto-Seed (For Docker/CI/Development)

Set environment variables:
```env
ADMIN_EMAIL=admin@poruta.io
ADMIN_PASSWORD=Str0ng!Adm1n#Pass
```

On first startup, if no admin exists, one is created automatically. Subsequent startups skip this.

---

## First Login

1. Admin goes to `/login`
2. Enters CLI-created or auto-seeded credentials
3. `POST /auth/login` → 200 with tokens
4. `profile_completed: true` → direct to Admin Dashboard

No email verification needed. No profile completion needed. Immediate access.

---

## Admin Responsibilities (Auth-Related)

### 1. Create Agencies

Before agency managers can onboard, their agencies must exist.

**Flow:**
1. Go to Agency Management
2. Click "Add Agency"
3. Enter: name, registration number, address, phone, email
4. `POST /auth/agencies` → 201
5. Agency is now available for managers to select during profile completion

### 2. Invite Government Officials

**Flow:**
1. Go to User Management
2. Click "Invite User"
3. Enter email, select role: "Government RRA" or "Government RSB"
4. `POST /auth/invite` → 201
5. Government official receives invitation email

### 2b. Universal Invitation (Any Role)

Admin can invite **any** role in the system — not just Government officials.

**Supported invitation targets:** `importer`, `agent`, `agency_manager`, `inspector`, `government_rra`, `government_rsb`

**Flow:**
1. Go to User Management → "Invite User"
2. Enter email, select any role from the list above
3. If inviting an `agent`, also select the target agency (admin can assign to any agency)
4. `POST /auth/invite` → 201
5. User receives invitation email with a registration link

> Agency managers can invite agents. Government RRA/RSB officials can invite their own respective roles. Admin can invite all non-admin roles.

### 3. Monitor System via Audit Logs

**Flow:**
1. Go to Audit Logs
2. `GET /auth/logs?action=FAILED_LOGIN&date_from=today`
3. See all failed login attempts — identify brute force attacks
4. Filter by user, action, date range, IP address

### 4. Manage Users

**View all users:**
- `GET /auth/users?page=1&role=agent&search=Marie`
- See every user in the system with their role and status

**Deactivate a user:**
- `PATCH /auth/users/{id}/deactivate` → user can no longer log in
- All their sessions are revoked immediately
- Use case: employee leaves, security concern, compliance requirement

**Reactivate a user:**
- `PATCH /auth/users/{id}/activate` → user can log in again

### 5. Manage Agencies

- View all agencies with member counts
- Update agency details (name, contact info)
- Deactivate agencies (soft-delete)

---

## Shadow Mode

Admin can "shadow" any non-admin user — acting as that user to debug issues, verify permissions, or assist with support requests. Shadow mode provides full access to everything the target user can see and do.

### How It Works

1. Admin selects a user to shadow
2. `POST /admin/shadow/{user_id}` → returns a **shadow token**
3. The shadow token is a standard JWT access token with two extra claims:
   - `shadow_admin_id` — the admin's user ID
   - `shadow_admin_email` — the admin's email
4. The frontend uses this token instead of the admin's own token
5. All API requests work as if the admin is the target user

### Starting a Shadow Session

```
POST /admin/shadow/{user_id}
Authorization: Bearer <admin_access_token>
```

**Response:**
```json
{
  "shadow_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 900,
  "target_user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "agent"
  },
  "message": "Shadow session started for user@example.com"
}
```

### Ending a Shadow Session

```
POST /admin/shadow/end
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{"shadowed_user_id": "uuid"}
```

### Shadow Constraints

| Constraint | Details |
|-----------|---------|
| Cannot shadow other admins | Prevented — returns 403 |
| Cannot shadow deactivated users | Prevented — returns 400 |
| Token expiry | Same as regular access tokens (15 minutes) |
| No refresh token | Shadow tokens are not refreshable — admin must start a new session |

### Auditing

Every shadow session generates two audit log entries:
- `SHADOW_START` — logged when admin starts the session (includes target user details)
- `SHADOW_END` — logged when admin explicitly ends the session

All HTTP requests made with a shadow token are tagged in server logs with `[SHADOW by admin@email]`.

### Frontend Integration

The frontend should:
1. Store the shadow token separately from the admin's own token
2. Display a prominent banner: "You are shadowing user@example.com"
3. When ending shadow mode, call `POST /admin/shadow/end` then restore the admin's original token

---

## Admin Restrictions

Even admins have boundaries:

| Action | Allowed? | Reason |
|--------|----------|--------|
| Create another admin via web | No | CLI/seed only — prevents web-based admin escalation |
| Deactivate another admin | No | Prevents admin power struggles — one rogue admin can't lock out all others |
| Self-deactivate | No | Would lock themselves out |
| Invite admin via invitation system | No | Admin creation is a server-side operation |
| Invite any other role | Yes | Admin can invite importer, agent, agency_manager, inspector, government_rra, government_rsb |
| Shadow any non-admin user | Yes | Full access shadow mode with audit trail |
| Shadow another admin | No | Admin-to-admin shadowing is blocked |
| Access importer's payment data | Per permissions | Auth service manages identity, not data access |

---

## Day-to-Day Authentication

Standard login/session mechanics apply.

### Admin Session Security Considerations

Admins have elevated privileges, so session security is critical:
- Same 15-min access token, 7-day refresh token
- Account lockout after 5 failed attempts
- All admin actions are logged in auth_logs

---

## The Admin Bootstrap Problem

"Who creates the first admin?" is a chicken-and-egg problem. Poruta solves it with:

```
System deploys → Auto-seed creates first admin from env vars
First admin logs in → Creates agencies, invites government_rra/government_rsb users  
Government RRA/RSB users onboard → Invite their own role members
Agency managers self-register → Select their agency → Invite agents
Importers self-register → Start using the platform
```

The env-var auto-seed is the "genesis event" — it only runs once, only if no admin exists, and only if the env vars are set. After that, additional admins are created via CLI.

---

## Permissions Summary

| Resource | View | Create | Edit | Delete |
|----------|------|--------|------|--------|
| All Users | Yes | No (invite only) | No | No |
| User Activation | — | — | Yes | No |
| Agencies | Yes | Yes | Yes | Yes (soft) |
| Agency Members | Yes | No | No | No |
| Audit Logs | Yes | No | No | No |
| Invitations (all roles) | Yes | Yes | No | No |
| Own Profile | Yes | No | Yes | No |
| Shadow Mode | — | Yes (start) | — | Yes (end) |
| System Settings | — | — | — | — |
