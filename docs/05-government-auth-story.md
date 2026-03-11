# Government Official Authentication Story

## Who is the Government Official?

Government officials oversee customs operations at a national level. There are two distinct types:

- **RRA Officials** (`government_rra`) — Rwanda Revenue Authority officers who verify customs declarations, review tax breakdowns, collect duties, and clear shipments. Maps to backend roles: `STAKEHOLDER_RRA` / `STAKEHOLDER_ADMIN_RRA`.
- **RSB Officials** (`government_rsb`) — Rwanda Standards Board officers who review product certificates, verify compliance with quality/safety standards, and approve or flag imports. Maps to backend roles: `STAKEHOLDER_RSB` / `STAKEHOLDER_ADMIN_RSB`.

Both types are invited by System Admins. RRA officials can invite other RRA officials. RSB officials can invite other RSB officials.

---

## Registration Journey

### Step 0: Admin Sends Invitation

1. System Admin logs into Poruta
2. Goes to user management
3. Enters the government official's email
4. Selects role: "Government (RRA)" or "Government (RSB)"
5. Clicks "Send Invitation"
6. `POST /api/v1/invitations/create` with `{email, role: "government_rra"}` or `{email, role: "government_rsb"}`

The official receives:
```
Subject: You've been invited to join Poruta
"The System Administrator has invited you to join Poruta as an RRA Official."
[Accept Invitation] → {frontend}/signup/invite?token=def456
"This invitation expires in 24 hours."
```

### Step 1: Click Invitation Link

1. Browser opens `/signup/invite?token=def456`
2. Frontend calls `GET /api/v1/invitations/validate/def456`
3. Response: `{email, role: "government_rra", invited_by: {name: "System Administrator"}}`
4. Frontend displays:
   - "You've been invited to join Poruta as an RRA Official"
   - Email (pre-filled, read-only)

### Step 2: Complete Signup

**What they fill in:**
- Password
- First Name
- Last Name
- Phone Number

**What happens:**
- `POST /api/v1/invitations/signup` → 201
- Account: `is_email_verified=true`, `profile_completed=true`
- Auto-logged in → redirect to Government Dashboard

---

## Core Responsibility: Inviting Inspectors

Once onboarded, the Government official's primary auth-related action is inviting inspectors:

1. Go to personnel management
2. Enter inspector's email
3. Click "Invite Inspector"
4. `POST /auth/invite` with `{email, role: "inspector"}`
5. Inspector receives invitation email

**They can track:**
- Pending inspector invitations
- Active inspectors in the system
- Inspector assignment and workload (via main backend)

---

## Trust Chain Position

```
Admin
  ├── invites → Government Official
  └── manages → Agencies

Government Official
  └── invites → Inspector

Agency Manager (self-signup)
  └── invites → Agent
```

The Government role is the bridge between system administration and field operations. They don't manage agencies or importers — they manage the inspection workforce.

---

## Day-to-Day Authentication

Standard login/session mechanics. See Importer story for details.

### Government Dashboard Features

- National trade analytics and KPIs
- Inspector workforce management
- Compliance monitoring
- Regulatory reporting tools

---

## What Government Officials Cannot Do

- **Cannot self-register**: Invited by admin only
- **Cannot manage agencies**: That's the admin's job
- **Cannot manage importers/agents**: Agency-side users
- **Cannot access admin functions**: User management, audit logs
- **Cannot invite government peers**: Only admin can invite government users

---

## Permissions Summary

| Resource | View | Create | Edit | Delete |
|----------|------|--------|------|--------|
| Analytics Dashboard | ✅ | ❌ | ❌ | ❌ |
| All Declarations (read-only, aggregated) | ✅ | ❌ | ❌ | ❌ |
| Inspector Management | ✅ | ❌ | ❌ | ❌ |
| Inspector Invitations | ✅ | ✅ | ❌ | ❌ |
| Trade Reports | ✅ | ✅ | ❌ | ❌ |
| Own Profile | ✅ | ❌ | ✅ | ❌ |
| User Management | ❌ | ❌ | ❌ | ❌ |
| Agency Management | ❌ | ❌ | ❌ | ❌ |
| Audit Logs | ❌ | ❌ | ❌ | ❌ |
