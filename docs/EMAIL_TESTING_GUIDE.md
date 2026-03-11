# Email Verification Testing Guide

## Overview

This guide explains how to test the complete authentication flow with real email sending. Email verification is currently **disabled** for development convenience, but this guide shows you how to enable and test it.

---

## Option 1: Test with Real SMTP (Production-like)

### Step 1: Get SMTP Credentials

Choose an email service provider:

#### **Gmail (Free, for testing)**
1. Enable 2-factor authentication on your Google account
2. Generate an "App Password": https://myaccount.google.com/apppasswords
3. Use these settings:
   ```env
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your.email@gmail.com
   SMTP_PASSWORD=your-app-password
   SMTP_FROM_EMAIL=your.email@gmail.com
   SMTP_FROM_NAME=Poruta
   ```

#### **SendGrid (Free tier: 100 emails/day)**
1. Sign up at https://sendgrid.com
2. Create an API key with "Mail Send" permission
3. Use these settings:
   ```env
   SMTP_HOST=smtp.sendgrid.net
   SMTP_PORT=587
   SMTP_USERNAME=apikey
   SMTP_PASSWORD=your-sendgrid-api-key
   SMTP_FROM_EMAIL=noreply@yourdomain.com
   SMTP_FROM_NAME=Poruta
   ```

#### **Zoho Mail (Free for personal domain)**
1. Sign up at https://zoho.com/mail
2. Generate an app-specific password
3. Use these settings:
   ```env
   SMTP_HOST=smtp.zoho.com
   SMTP_PORT=587
   SMTP_USERNAME=noreply@yourdomain.com
   SMTP_PASSWORD=your-app-password
   SMTP_FROM_EMAIL=noreply@yourdomain.com
   SMTP_FROM_NAME=Poruta
   ```

### Step 2: Update Backend Configuration

Edit `auth_services/.env`:

```env
# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your.email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your.email@gmail.com
SMTP_FROM_NAME=Poruta
```

### Step 3: Re-enable Email Verification

**File: `auth_services/src/services/auth_service.py`**

#### Change 1: Signup function (around line 136-154)

```python
# Find this line:
is_email_verified=True,  # ← Currently True

# Change to:
is_email_verified=False,  # ← Change to False

# Find these commented lines (around line 148-154):
# raw_token = generate_token()
# evt = EmailVerificationToken(
#     user_id=user.id,
#     token_hash=hash_token(raw_token),
#     expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
# )
# db.add(evt)
# await db.flush()
# await email_service.send_verification_email(email, raw_token)

# Uncomment them (remove the # at the start of each line)
```

#### Change 2: Login function (around line 298)

```python
# Add this check before the "Success" comment:
if not user.is_email_verified:
    raise AuthorizationError("Please verify your email address before logging in.")
```

### Step 4: Update Frontend Signup Page

**File: `poruta-front-end/src/app/(standalone)/signup/page.tsx`**

Find this code (around line 40-50):

```typescript
// Current code:
await signupWithCredentials(email, password, role);
router.push('/login');

// Change to:
const result = await signupWithCredentials(email, password, role);
setSuccess(result.message); // Shows "Check your email" message
// Remove: router.push('/login');
```

### Step 5: Restart Backend

```powershell
# Stop the backend (Ctrl+C in the terminal running it)

# Start it again
cd "c:\Users\Admin\OneDrive\Desktop\Poruta\auth_services"
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn src.main:app --host 0.0.0.0 --port 8050 --reload
```

### Step 6: Test the Flow

1. **Signup:**
   - Go to http://localhost:9000/signup
   - Enter a REAL email address you have access to
   - Submit the form
   - You should see: "Account created! Check your email to verify your account."

2. **Check Email:**
   - Open your email inbox
   - You should receive an email with subject "Verify Your Email - Poruta"
   - Click the verification link

3. **Login:**
   - Go to http://localhost:9000/login
   - Try logging in BEFORE verifying email → Should show error
   - After clicking verification link, try again → Should succeed

---

## Option 2: Test with MailHog (Recommended for Development)

MailHog is a fake SMTP server that captures emails instead of sending them. Perfect for testing!

### Step 1: Install MailHog

**Windows (Chocolatey):**
```powershell
choco install mailhog
```

**Or download manually:**
- Download from: https://github.com/mailhog/MailHog/releases
- Run `MailHog.exe`

### Step 2: Configure Backend

Edit `auth_services/.env`:

```env
# MailHog SMTP Configuration
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=noreply@poruta.local
SMTP_FROM_NAME=Poruta
```

### Step 3: Start MailHog

Open a new PowerShell terminal:

```powershell
mailhog
```

Or if you downloaded manually:
```powershell
.\MailHog.exe
```

**MailHog will start:**
- SMTP server on port 1025 (for sending emails)
- Web UI on http://localhost:8025 (to view emails)

### Step 4: Follow Steps 3-6 from Option 1

Re-enable verification in the code, restart backend, and test signup.

### Step 5: View Captured Emails

- Open http://localhost:8025 in your browser
- You'll see all "sent" emails listed
- Click to read and copy verification links
- No real emails are sent!

---

## Option 3: Test with Mailtrap (Cloud Development SMTP)

Mailtrap is like MailHog but cloud-based. Good if you can't install software locally.

### Step 1: Sign Up

1. Go to https://mailtrap.io
2. Create a free account (500 emails/month)
3. Go to "Email Testing" → "Inboxes" → "My Inbox"
4. Copy SMTP credentials

### Step 2: Configure Backend

Edit `auth_services/.env`:

```env
# Mailtrap SMTP Configuration
SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=2525
SMTP_USERNAME=your-mailtrap-username
SMTP_PASSWORD=your-mailtrap-password
SMTP_FROM_EMAIL=noreply@poruta.local
SMTP_FROM_NAME=Poruta
```

### Step 3: Follow Steps 3-6 from Option 1

Re-enable verification, restart backend, and test.

### Step 4: View Emails in Mailtrap

- Open https://mailtrap.io
- Go to your inbox
- View captured emails and click verification links

---

## Testing Invitation Emails

After enabling email verification, you can also test invitation emails:

1. **Admin creates agency:**
   - Login as admin
   - Go to `/agencies`
   - Create a test agency

2. **Admin invites government official:**
   - Go to `/invitations`
   - Invite a test email address

3. **Check email:**
   - The invited user receives an invitation email
   - Click the link to signup with pre-filled email and role
   - Account is automatically verified (no verification email)

4. **Government invites inspector:**
   - Login as government official
   - Go to `/invitations`
   - Invite inspector

5. **Manager invites agent:**
   - Signup as agency manager
   - Complete profile (select agency)
   - Go to `/invitations`
   - Invite agent (must belong to same agency)

---

## Troubleshooting

### Emails not sending?

**Check 1: SMTP credentials**
```powershell
# Test SMTP connection from Python
python -c "
import smtplib
from email.mime.text import MIMEText

server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login('your.email@gmail.com', 'your-app-password')
print('✓ SMTP connection successful!')
server.quit()
"
```

**Check 2: Backend logs**

Look for errors in the terminal running the backend:
```
ERROR - Failed to send email: ...
```

**Check 3: Firewall/Antivirus**

Some firewalls block SMTP ports. Try disabling temporarily.

### Gmail "Less secure app" error?

You need to use an App Password, not your regular password:
1. Enable 2-factor authentication
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use that password in SMTP_PASSWORD

### MailHog not receiving emails?

1. Check MailHog is running: http://localhost:8025
2. Check SMTP_PORT=1025 in .env
3. Check SMTP_HOST=localhost in .env

---

## Reverting to Disabled State

To disable email verification again:

```python
# In auth_services/src/services/auth_service.py:
is_email_verified=True,  # Back to True
# Comment out the email sending code again
```

```typescript
// In poruta-front-end/src/app/(standalone)/signup/page.tsx:
await signupWithCredentials(email, password, role);
router.push('/login');  // Redirect instead of showing message
```

---

## Summary

| Option | Pros | Cons | Best For |
|--------|------|------|----------|
| **Real SMTP** | Production-like, real delivery | Need credentials, rate limits | Final testing |
| **MailHog** | Local, fast, no limits | Need to install | Development |
| **Mailtrap** | Cloud, no install, web UI | 500/month limit | Quick testing |

**Recommendation:** Use MailHog for development, then test with real SMTP before production.
