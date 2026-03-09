# Importer Authentication Story

## Who is the Importer?

An importer is a business entity (individual or company) that imports goods into the country and needs to clear them through customs. They interact with the Poruta platform to submit customs declarations, track shipment progress, upload documents, and pay duties/fees.

---

## Registration Journey

The importer self-registers. There is no invitation — anyone with a valid email can sign up as an importer.

### Step 1: Signup Page (`/signup`)

**What they see:**
- Email field
- Password field (with strength indicator showing requirements)
- Role selector: "Importer" or "Agency Manager" (only two self-signup roles)
- "Create Account" button
- Link to login page: "Already have an account?"

**What they do:**
1. Enter business email (e.g., `jp@kigalielec.rw`)
2. Create a strong password (12+ chars, upper, lower, digit, special)
3. Select "Importer" as their role
4. Click "Create Account"

**What happens:**
- `POST /auth/signup` → 201
- Account created with `is_email_verified=false`, `profile_completed=false`
- Verification email sent to `jp@kigalielec.rw`
- Redirect to "Check Your Email" page

### Step 2: Email Verification

**What they receive:**
```
Subject: Verify your Poruta account
"Click the button below to verify your email address."
[Verify Email Address] → {frontend}/verify-email?token=abc123
"This link expires in 24 hours."
```

**What they do:**
1. Open email, click "Verify Email Address"
2. Browser opens `/verify-email?token=abc123`
3. Frontend calls `POST /auth/verify-email` with the token
4. Success page: "Email verified! Please log in to continue."

**If the link expires:**
- The verification page shows "This link has expired"
- A "Resend Verification Email" button is available
- Clicking it calls `POST /auth/verify-email/resend` → new email sent

### Step 3: First Login

**What they do:**
1. Go to `/login`
2. Enter email and password
3. Click "Log In"

**What happens:**
- `POST /auth/login` → 200 with tokens
- User object shows `profile_completed: false`
- Frontend detects incomplete profile → redirect to `/onboarding/profile`

### Step 4: Profile Completion (`/onboarding/profile`)

**What the importer sees:**
- First Name field
- Last Name field
- Phone Number field
- Company Name field **← required for importers**
- "Complete Profile" button

**What they do:**
1. Fill in personal details and their company name (e.g., "Kigali Electronics Ltd")
2. Click "Complete Profile"

**What happens:**
- `POST /auth/profile/complete` → 200
- `profile_completed` set to `true`
- Redirect to Importer Dashboard

### Step 5: Platform Access (Fully Onboarded)

The importer can now access:
- `/dashboard` — their personal dashboard
- `/declarations` — submit and manage customs declarations
- `/shipments` — track shipment status
- `/documents` — upload supporting documents
- `/payments` — view and pay duties/fees
- `/profile` — update their profile information

---

## Day-to-Day Authentication

### Returning Login
1. Go to `/login`
2. Enter email + password
3. Redirected to Importer Dashboard
4. Session persists for up to 7 days (refresh token)

### Session Expiry
- After 15 minutes of API inactivity, the access token expires
- The frontend automatically refreshes it using the refresh token cookie
- After 7 days without any activity, the refresh token expires
- User is redirected to `/login`

### Page Reload
- Access token is in memory (lost on reload)
- Frontend calls `/auth/refresh` on page load
- If refresh succeeds → session restored seamlessly
- If refresh fails → redirect to `/login`

---

## Password Management

### Forgot Password
1. Click "Forgot Password?" on login page
2. Enter email address
3. System always says "If an account exists, we've sent a reset link"
4. Email arrives with reset link (valid for 1 hour)
5. Click link → `/reset-password?token=xxx`
6. Enter new password → account unlocked, all other sessions revoked
7. Log in with new password

### Change Password (While Logged In)
1. Go to Profile/Settings
2. Enter current password + new password
3. All other sessions are logged out
4. Current session remains active

---

## Account Lockout

If someone enters the wrong password 5 times:
1. Account is locked for 15 minutes
2. Login attempts during lockout period are rejected with "Account temporarily locked"
3. After 15 minutes, the account automatically unlocks
4. Alternatively, a password reset via email unlocks immediately

---

## Permissions Summary

| Resource | View | Create | Edit | Delete |
|----------|------|--------|------|--------|
| Own Declarations | ✅ | ✅ | ✅ | ❌ |
| Own Shipments | ✅ | ❌ | ❌ | ❌ |
| Own Documents | ✅ | ✅ | ❌ | ❌ |
| Own Payments | ✅ | ❌ | ❌ | ❌ |
| Own Profile | ✅ | ❌ | ✅ | ❌ |
| Other Users | ❌ | ❌ | ❌ | ❌ |
| Agencies | ❌ | ❌ | ❌ | ❌ |
| Audit Logs | ❌ | ❌ | ❌ | ❌ |
