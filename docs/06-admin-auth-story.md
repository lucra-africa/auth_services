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
3. Enter email, select role: "Government"
4. `POST /auth/invite` → 201
5. Government official receives invitation email

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

## Admin Restrictions

Even admins have boundaries:

| Action | Allowed? | Reason |
|--------|----------|--------|
| Create another admin via web | ❌ | CLI/seed only — prevents web-based admin escalation |
| Deactivate another admin | ❌ | Prevents admin power struggles — one rogue admin can't lock out all others |
| Self-deactivate | ❌ | Would lock themselves out |
| Invite admin via invitation system | ❌ | Admin creation is a server-side operation |
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
First admin logs in → Creates agencies, invites government users  
Government users onboard → Invite inspectors
Agency managers self-register → Select their agency → Invite agents
Importers self-register → Start using the platform
```

The env-var auto-seed is the "genesis event" — it only runs once, only if no admin exists, and only if the env vars are set. After that, additional admins are created via CLI.

---

## Permissions Summary

| Resource | View | Create | Edit | Delete |
|----------|------|--------|------|--------|
| All Users | ✅ | ❌ (invite only) | ❌ | ❌ |
| User Activation | — | — | ✅ | ❌ |
| Agencies | ✅ | ✅ | ✅ | ✅ (soft) |
| Agency Members | ✅ | ❌ | ❌ | ❌ |
| Audit Logs | ✅ | ❌ | ❌ | ❌ |
| Invitations (govt) | ✅ | ✅ | ❌ | ❌ |
| Own Profile | ✅ | ❌ | ✅ | ❌ |
| System Settings | — | — | — | — |
