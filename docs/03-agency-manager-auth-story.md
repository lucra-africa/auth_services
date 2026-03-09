# Agency Manager Authentication Story

## Who is the Agency Manager?

An agency manager runs a customs clearing agency. They manage a team of customs agents, oversee declaration processing, handle agency billing, and ensure compliance. Agency Managers self-register, but must associate with an existing agency (created by the admin).

---

## Registration Journey

### Step 1: Signup Page (`/signup`)

**What they see:**
- Email field
- Password field
- Role selector: "Importer" or "Agency Manager"
- "Create Account" button

**What they do:**
1. Enter their email
2. Create a strong password
3. Select "Agency Manager" as their role
4. Click "Create Account"

**What happens:**
- `POST /auth/signup` → 201
- Account created with `is_email_verified=false`, `profile_completed=false`
- Verification email sent
- Redirect to "Check Your Email" page

### Step 2: Email Verification

Same flow as importers. Click link in email → email verified → "Please log in."

### Step 3: First Login

- Login with email + password
- `profile_completed: false` → redirected to `/onboarding/profile`

### Step 4: Profile Completion (`/onboarding/profile`)

**What the Agency Manager sees (different from importers):**
- First Name
- Last Name
- Phone Number
- **Agency dropdown/search** ← instead of company_name, manager selects an agency
- "Complete Profile" button

**The agency dropdown** is populated by `GET /auth/agencies` which returns all active agencies. The manager searches for their agency by name and selects it.

**What if no agencies exist?**
- The dropdown is empty
- A message appears: "No agencies available. Contact the system administrator to register your agency."
- The manager must wait for the admin to create their agency
- They can log in later to complete the profile

**What they do:**
1. Fill in personal details
2. Select their agency from the list
3. Click "Complete Profile"

**What happens:**
- `POST /auth/profile/complete` with `agency_id`
- UserProfile created, UserAgency record created (role: "manager")
- `profile_completed` set to `true`
- Redirect to Agency Manager Dashboard

---

## Core Responsibility: Inviting Agents

Once onboarded, the Agency Manager's primary auth-related action is inviting agents:

1. Go to Team Management page
2. Enter agent's email address
3. Click "Send Invitation"
4. `POST /auth/invite` with `{email, role: "agent"}` (agency_id is auto-resolved from manager's record)
5. Agent receives invitation email

**Manager can track:**
- Pending invitations (sent but not yet accepted)
- Active agents in their agency
- Agent activity (via the main backend, not auth service)

---

## Day-to-Day Authentication

Same login/session/refresh mechanics as all other roles.

### What the Agency Manager Dashboard Shows

- Overview of their agency's operations
- Team member list (agents)
- Pending invitations
- Declaration metrics for their agency

---

## Important Constraints

### Cannot Create Their Own Agency
- Agencies are admin-created with registration numbers and verification
- Manager only associates with existing agencies
- Prevents unauthorized agency creation

### One Agency Only
- A manager is linked to one agency via `user_agency`
- Cannot switch agencies without admin intervention
- This simplifies authorization — all agency-scoped queries filter by the manager's `agency_id`

### Cannot Invite Other Managers
- Only admins can create additional managers (via invitation or new signup + profile completion)
- A manager inviting another manager would bypass the admin-controlled organizational structure

---

## Agency Deactivation Impact

If the admin deactivates the agency:
- Manager can still log in
- Manager cannot invite new agents (POST /auth/invite returns error)
- Manager's dashboard shows agency as inactive
- Existing agents under this agency are NOT automatically deactivated

---

## Permissions Summary

| Resource | View | Create | Edit | Delete |
|----------|------|--------|------|--------|
| Own Agency | ✅ | ❌ | ❌ | ❌ |
| Agency Agents | ✅ | ❌ | ❌ | ❌ |
| Agent Invitations | ✅ | ✅ | ❌ | ❌ |
| Declarations (own agency) | ✅ | ❌ | ❌ | ❌ |
| Own Profile | ✅ | ❌ | ✅ | ❌ |
| Other Agencies | ❌ | ❌ | ❌ | ❌ |
| All Users | ❌ | ❌ | ❌ | ❌ |
| Audit Logs | ❌ | ❌ | ❌ | ❌ |
