# Step 09 — Admin Seeding & CLI

> **Phase**: D (Admin & Agency)  
> **Dependencies**: Phase B (core auth)  
> **Produces**: CLI for admin creation, auto-seed on first startup

---

## Objective

Provide two mechanisms for creating System Admin accounts — neither involving a web signup form. Admins are the root-of-trust in the system: they create agencies, invite government users, and manage all accounts. The admin creation path must be completely separate from the public-facing authentication flow.

---

## Two Admin Creation Methods

### Method 1: CLI Command

```bash
python -m src.cli create-admin \
  --email admin@poruta.io \
  --password "Str0ng!Adm1n#Pass" \
  --first-name System \
  --last-name Administrator
```

**When to use**: Production environments, creating additional admins, explicit and auditable.

### Method 2: Environment Variable Auto-Seed

If `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set in `.env` AND no admin account exists in the database, automatically create one on service startup.

**When to use**: Development environments, Docker first-run, CI/CD pipelines.

---

## File to Create

```
auth_services/src/cli.py
```

Plus modification to `main.py` to add auto-seed logic in the lifespan handler.

---

## CLI Design (cli.py)

Using Python's stdlib `argparse` (no `click` or `typer` dependency):

```python
# Usage: python -m src.cli create-admin --email x --password y --first-name z --last-name w
#
# Steps:
# 1. Parse arguments
# 2. Validate password strength (same rules as user signup)
# 3. Connect to database (using same config as the main app)
# 4. Check if email already exists → error if yes
# 5. Create User:
#    - email, password_hash (Argon2id)
#    - role = admin
#    - is_email_verified = true (admin doesn't need email verification)
#    - is_active = true
#    - profile_completed = true
# 6. Create UserProfile:
#    - first_name, last_name
#    - phone = null
#    - company_name = null
# 7. Log ADMIN_CREATED action (ip_address = "cli", user_agent = "cli")
# 8. Print success message with email
```

### CLI Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--email` | Yes | Admin email address |
| `--password` | Yes | Admin password (must pass strength validation) |
| `--first-name` | Yes | Admin first name |
| `--last-name` | Yes | Admin last name |

### CLI Output

```
✓ Admin account created successfully
  Email: admin@poruta.io
  Role: admin
  Status: Active, email verified, profile complete

⚠ Keep these credentials safe. This is the only time the password is shown in plaintext.
```

If the email already exists:
```
✗ Error: An account with email admin@poruta.io already exists.
```

If the password is too weak:
```
✗ Error: Password does not meet requirements:
  - Must be at least 12 characters
  - Must contain a special character
```

---

## Auto-Seed Logic (in main.py lifespan)

```python
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await auto_seed_admin()  # ← new
    yield
    # Shutdown
    await close_db()

async def auto_seed_admin():
    """Create admin from env vars if no admin exists."""
    if not settings.admin_email or not settings.admin_password:
        return  # No env vars set — skip silently
    
    async with get_db_session() as db:
        # Check if ANY admin account exists
        admin_exists = await db.execute(
            select(User).where(User.role == UserRole.ADMIN).limit(1)
        )
        if admin_exists.scalar():
            return  # Admin already exists — skip
        
        # Validate password
        violations = validate_password_strength(settings.admin_password)
        if violations:
            logger.warning(f"Admin auto-seed skipped: password too weak ({violations})")
            return
        
        # Create admin (same logic as CLI)
        # Log ADMIN_CREATED (ip_address = "auto-seed", user_agent = "startup")
        logger.info(f"Auto-seeded admin account: {settings.admin_email}")
```

### Safety Mechanisms

1. **Only runs if no admin exists**: Once any admin is created (CLI or auto-seed), the auto-seed becomes a no-op. This prevents accidental admin duplication.
2. **Password validation still applies**: Weak passwords in env vars are rejected with a warning log.
3. **Logged**: The auto-seed action is logged to auth_logs with source "startup" — visible in the admin audit log.
4. **No env var cleanup**: The service doesn't delete the env vars after seeding. The administrator should remove `ADMIN_PASSWORD` from the environment after initial setup. A warning is logged if the env var is still present after the admin already exists.

---

## Why Not a Web-Based Setup Wizard?

A web-based first-run wizard (e.g., `/setup` page that creates the first admin) has a critical race condition:

1. Service starts with no admin
2. Attacker hits `/setup` before the legitimate administrator
3. Attacker creates their own admin account
4. Attacker owns the system

This is a well-known vulnerability class. The CLI and env-var approaches both require server access — if an attacker has server access, you have bigger problems.

---

## Admin Capabilities Summary

Once created, admins can:

| Action | Endpoint |
|--------|----------|
| Create agencies | POST /auth/agencies |
| Invite government users | POST /auth/invite |
| View all users | GET /auth/users |
| Deactivate any non-admin user | PATCH /auth/users/{id}/deactivate |
| Reactivate users | PATCH /auth/users/{id}/activate |
| View audit logs | GET /auth/logs |
| Manage agencies | PATCH/DELETE /auth/agencies/{id} |

**Cannot**:
- Deactivate another admin (prevents admin power struggles)
- Self-register via the web (no admin option on signup)
- Be invited via the invitation system (CLI/seed only)

---

## Acceptance Criteria

- [ ] `python -m src.cli create-admin` creates an admin account with correct flags
- [ ] CLI validates password strength (rejects weak passwords)
- [ ] CLI rejects duplicate email
- [ ] Auto-seed creates admin when env vars set and no admin exists
- [ ] Auto-seed is a no-op when an admin already exists
- [ ] Auto-seed is a no-op when env vars are not set
- [ ] Auto-seed logs a warning for weak passwords
- [ ] ADMIN_CREATED action logged for both CLI and auto-seed
- [ ] Admin can log in immediately after creation (verified, complete, active)
