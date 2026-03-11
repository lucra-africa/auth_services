# Inspector Authentication Story

## Who is the Inspector?

A warehouse inspector physically inspects goods at warehouses and border crossings, verifies documentation against physical shipments, and approves or rejects customs declarations. Maps to backend role: `STAKEHOLDER_WAREHOUSE`. Inspectors are invited by System Admins.

---

## Registration Journey

### Step 0: Admin Sends Invitation

A System Admin invites the inspector:
1. Admin logs into Poruta
2. Goes to user management
3. Enters inspector's email
4. Selects role: "Inspector"
5. Clicks "Send Invitation"
6. `POST /api/v1/invitations/create` with `{email, role: "inspector"}`

The inspector receives:
```
Subject: You've been invited to join Poruta
"The System Administrator has invited you to join Poruta as a Warehouse Inspector."
[Accept Invitation] → {frontend}/signup/invite?token=abc123
"This invitation expires in 24 hours."
```

### Step 1: Click Invitation Link

1. Browser opens `/signup/invite?token=abc123`
2. Frontend calls `GET /auth/invite/validate?token=abc123`
3. Response: `{email, role: "inspector", invited_by: {name: "Ministry Official"}}`
4. Frontend displays:
   - "You've been invited to join Poruta as a Customs Inspector"
   - Email (pre-filled, read-only)
   - Role: Customs Inspector (read-only)

### Step 2: Complete Signup

**What the inspector fills in:**
- Password
- First Name
- Last Name
- Phone Number

**What happens:**
- `POST /auth/signup/invited` → 201
- Account: `is_email_verified=true`, `profile_completed=true`
- No agency linkage (inspectors work for the government, not agencies)
- Auto-logged in → redirect to Inspector Dashboard

### One-step onboarding

Like agents, inspectors go from invitation email to fully operational in a single form submission. No verification steps, no profile completion page.

---

## Day-to-Day Authentication

Standard login/session mechanics apply. See Importer story for details.

### Inspector-Specific Context

Inspectors have unique access needs:
- Must access inspection queues and schedules
- Need to verify documents against physical goods
- Must submit inspection reports and decisions
- May work offline (future consideration — not in auth v1)

---

## Role in the Trust Chain

```
Admin creates system → invites Government officials
Government officials → invite Inspectors
Inspectors → cannot invite anyone
```

This mirrors the real-world hierarchy: the government appoints inspectors. Random people cannot become inspectors by self-registering.

---

## What Inspectors Cannot Do

- **Cannot self-register**: No "Inspector" option on signup page
- **Cannot invite anyone**: Inspectors are end-of-chain
- **Cannot access admin/agency functions**: No user management, no agency management
- **Cannot modify declarations**: They approve/reject, not edit
- **Cannot see payment/financial data**: Beyond their jurisdiction

---

## Permissions Summary

| Resource | View | Create | Edit | Delete |
|----------|------|--------|------|--------|
| Assigned Inspections | ✅ | ❌ | ❌ | ❌ |
| Inspection Reports | ✅ | ✅ | ✅ | ❌ |
| Declaration Documents | ✅ (read only) | ❌ | ❌ | ❌ |
| Approval/Rejection | ❌ | ✅ | ❌ | ❌ |
| Own Profile | ✅ | ❌ | ✅ | ❌ |
| Audit Logs | ❌ | ❌ | ❌ | ❌ |
| User Management | ❌ | ❌ | ❌ | ❌ |
