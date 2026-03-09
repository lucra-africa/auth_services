# Step 04 — User Registration (Self-Signup)

> **Phase**: B (Core Auth)  
> **Dependencies**: Steps 02 (models), 03 (security)  
> **Produces**: `POST /auth/signup` endpoint, email service

---

## Objective

Allow importers and agency managers to create accounts with email + password. Validate password strength, create the user record, generate an email verification token, and send a verification email via Zoho SMTP.

---

## Files to Create / Modify

```
auth_services/src/
├── api/
│   ├── __init__.py
│   ├── router.py              # Aggregates all route modules
│   └── auth.py                # POST /auth/signup (+ login/verify in later steps)
├── services/
│   ├── __init__.py
│   ├── auth_service.py        # signup() business logic
│   ├── email_service.py       # send_verification_email(), SMTP connection
│   └── log_service.py         # log_action() — audit log writer
└── templates/
    └── verify_email.html      # Email template (f-string based)
```

---

## Endpoint: POST /auth/signup

### Request
```json
{
  "email": "user@example.com",
  "password": "Str0ng!P@ssw0rd",
  "role": "importer"
}
```

**role** must be `"importer"` or `"agency_manager"`. Any other role returns 422 — this is the first defense against someone trying to self-register as an admin, inspector, agent, or government user.

### Validation Steps

1. **Email format**: Valid email via Pydantic `EmailStr` equivalent (regex check, no Pydantic[email] dependency — use manual regex)
2. **Email uniqueness**: Check `users` table — if exists, return 409
3. **Role restriction**: Only `importer` or `agency_manager` accepted
4. **Password strength**: Call `validate_password_strength()` — return 422 with specific violations if any

### Business Logic (auth_service.signup)

```
1. Validate password strength → raise ValidationError with violation list
2. Check email uniqueness → raise ConflictError("Email already registered")
3. Hash password with Argon2id
4. Create User record:
   - email, password_hash, role
   - is_email_verified=False
   - is_active=True
   - profile_completed=False
5. Generate verification token (secrets.token_urlsafe(32))
6. Hash token with SHA-256
7. Store EmailVerificationToken:
   - user_id, token_hash
   - expires_at = now + 24 hours
8. Send verification email (async, non-blocking)
9. Log SIGNUP action to auth_logs:
   - user_id, email, ip_address, user_agent
   - metadata: {"role": role}
10. Return success message
```

### Response (201)
```json
{
  "message": "Account created. Please check your email to verify your account.",
  "email": "user@example.com"
}
```

### Error Responses
| Code | Condition | Body |
|------|-----------|------|
| 409 | Email already registered | `{"error": "conflict", "message": "Email already registered"}` |
| 422 | Weak password | `{"error": "validation_error", "message": "Password does not meet requirements", "details": ["Must be at least 12 characters", "Must contain a special character"]}` |
| 422 | Invalid role | `{"error": "validation_error", "message": "Self-registration is only available for importer and agency_manager roles"}` |

---

## Email Service

### Design

```python
class EmailService:
    """Sends transactional emails via SMTP (Zoho)."""

    async def send_verification_email(self, to_email: str, token: str):
        """Build verification URL, render template, send via SMTP."""
        verify_url = f"{settings.frontend_url}/verify-email?token={token}"
        html = self._render_verify_email(to_email, verify_url)
        await self._send(to_email, "Verify your Poruta account", html)

    async def _send(self, to: str, subject: str, html_body: str):
        """Send email via SMTP using asyncio.to_thread() + stdlib smtplib."""
        # Uses smtplib.SMTP with STARTTLS on port 587
        # Connection: smtp.zoho.com:587
        # Auth: SMTP_USERNAME + SMTP_PASSWORD
        # From: SMTP_FROM_NAME <SMTP_FROM_EMAIL>
```

### Why stdlib smtplib + asyncio.to_thread()

The `smtplib` module is in Python's standard library. By wrapping it in `asyncio.to_thread()`, we get non-blocking email sending without adding the `aiosmtplib` dependency. The actual SMTP call runs in a thread pool while the event loop continues serving requests.

### Failure Handling

- If SMTP fails, log the error but **do not fail the signup**. The user can request a new verification email later.
- In development mode (`APP_ENV=development`), log the verification URL to console instead of sending email.

---

## Email Template (verify_email.html)

Simple HTML email with:
- Poruta branding (text-based, no images)
- "Hi [email]" greeting
- "Click below to verify your email address" message
- CTA button linking to `{frontend_url}/verify-email?token={token}`
- "This link expires in 24 hours" notice
- "If you didn't create an account, you can safely ignore this email" footer

Created as an f-string template in Python — no Jinja2 dependency.

---

## Audit Log Entry

```python
await log_service.log(
    action=AuthAction.SIGNUP,
    user_id=user.id,
    email=user.email,
    ip_address=request.client.host,
    user_agent=request.headers.get("user-agent"),
    metadata={"role": signup_request.role}
)
```

---

## Acceptance Criteria

- [ ] `POST /auth/signup` with valid importer data returns 201
- [ ] `POST /auth/signup` with `role: "admin"` returns 422
- [ ] `POST /auth/signup` with `role: "agent"` returns 422
- [ ] `POST /auth/signup` with existing email returns 409
- [ ] `POST /auth/signup` with weak password returns 422 with specific violation messages
- [ ] Email verification token is stored as SHA-256 hash (not plaintext)
- [ ] Verification email is sent (or logged in development mode)
- [ ] SIGNUP action appears in auth_logs with correct metadata
- [ ] User record has `is_email_verified=False`, `profile_completed=False`
