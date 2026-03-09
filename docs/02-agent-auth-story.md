# Custom Agent Authentication Story

## Who is the Custom Agent?

A customs agent is a licensed professional who works within a customs clearing agency. They process customs declarations on behalf of importers, review documents, calculate duties, and liaise between importers and government inspectors. Agents do NOT self-register — they are invited by their Agency Manager.

---

## Registration Journey

### Step 0: Agency Manager Sends Invitation

Before an agent can join, their Agency Manager must invite them:
1. Manager logs into Poruta
2. Goes to team management page
3. Enters the agent's email address
4. Clicks "Send Invitation"
5. System calls `POST /auth/invite` with `{email, role: "agent", agency_id: manager's agency}`

The agent receives an email:
```
Subject: You've been invited to join Poruta
"Patrick Ndayisaba has invited you to join Poruta as a Customs Agent.
You'll be joining Swift Customs Agency."
[Accept Invitation] → {frontend}/signup/invite?token=xyz789
"This invitation expires in 24 hours."
```

### Step 1: Click Invitation Link

**What happens when the agent clicks the link:**
1. Browser opens `/signup/invite?token=xyz789`
2. Frontend calls `GET /auth/invite/validate?token=xyz789`
3. Response includes: `{email, role: "agent", agency: {name: "Swift Customs Agency"}, invited_by: {name: "Patrick Ndayisaba"}}`
4. Frontend displays invitation info:
   - "You've been invited by Patrick Ndayisaba"
   - "Role: Customs Agent"
   - "Agency: Swift Customs Agency"
   - Email field (pre-filled, read-only)

### Step 2: Complete Signup Form

**What the agent sees:**
- Email (pre-filled, read-only)
- Role (shown as "Customs Agent", read-only)
- Agency (shown as "Swift Customs Agency", read-only)
- Password field (with strength requirements)
- First Name
- Last Name
- Phone Number
- "Join Poruta" button

**What they do:**
1. Choose a strong password
2. Enter their name and phone number
3. Click "Join Poruta"

**What happens:**
- `POST /auth/signup/invited` → 201
- Account created with `is_email_verified=true`, `profile_completed=true`
- Auto-linked to "Swift Customs Agency" via `user_agency` table
- Auto-logged in (tokens returned in response)
- Redirect to Agent Dashboard

### That's it — one-step onboarding

No email verification needed (the invitation email proves ownership).  
No profile completion step needed (details provided during signup).  
No agency selection needed (auto-linked to inviter's agency).

---

## Day-to-Day Authentication

Same login/session/refresh mechanics as all other roles. See Importer story for details.

### What the Agent Sees After Login

The agent is immediately taken to their Agent Dashboard:
- Assigned declarations to review
- Pending document reviews
- Tasks from their agency manager
- Chat with importers

---

## What Agents Cannot Do

- **Cannot self-register**: No "Agent" option on the public signup page
- **Cannot switch agencies**: Agency is set at invitation time (admin can reassign if needed)
- **Cannot invite anyone**: Only managers invite agents
- **Cannot access admin functions**: Audit logs, user management, agency management
- **Cannot see other agencies' data**: Data isolation per agency

---

## Invitation Edge Cases

### Expired Invitation (>24 hours)
- Agent clicks link → "/signup/invite?token=..."
- Frontend calls validate → 400 "Invitation has expired"
- Frontend shows: "This invitation has expired. Please contact your manager to send a new one."
- Manager can send a new invitation from their dashboard

### Already Used Invitation
- Agent (or someone) tries to use the link again after signup
- Frontend calls validate → 400 "This invitation has already been used"
- If the agent already has an account, they should log in instead

### Agent Already Has an Account
- Manager tries to invite email that's already registered
- `POST /auth/invite` → 409 "A user with this email already exists"
- Manager sees error and contacts the user directly

---

## Permissions Summary

| Resource | View | Create | Edit | Delete |
|----------|------|--------|------|--------|
| Assigned Declarations | ✅ | ❌ | ✅ | ❌ |
| Declaration Documents | ✅ | ✅ | ❌ | ❌ |
| Importer Chat | ✅ | ✅ | ❌ | ❌ |
| Own Profile | ✅ | ❌ | ✅ | ❌ |
| Agency Members | ✅ (read only) | ❌ | ❌ | ❌ |
| Other Agencies | ❌ | ❌ | ❌ | ❌ |
| Audit Logs | ❌ | ❌ | ❌ | ❌ |
