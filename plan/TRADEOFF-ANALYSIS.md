# Tradeoff Analysis — Poruta Authentication System

Every architectural decision has costs. This document dissects each choice: what we gain, what we lose, what alternatives exist, and why the chosen path is the right one for Poruta.

---

## Table of Contents

1. [Password Hashing: Argon2id vs bcrypt vs scrypt](#1-password-hashing)
2. [JWT Signing: HS256 vs RS256](#2-jwt-signing)
3. [Token Lifespans: 15-min access / 7-day refresh](#3-token-lifespans)
4. [Token Storage: SHA-256 Hashing in DB](#4-token-storage)
5. [Database: PostgreSQL Separate DB for Auth](#5-database-strategy)
6. [Framework: FastAPI](#6-framework)
7. [Async Everywhere](#7-async-architecture)
8. [Email Verification: Required for All](#8-email-verification)
9. [Invitation-Based Registration for Restricted Roles](#9-invitation-system)
10. [Admin Creation: CLI + Env-Var Hybrid](#10-admin-creation)
11. [Brute-Force Protection: Account Lockout vs Rate Limiting](#11-brute-force)
12. [Refresh Token Rotation](#12-refresh-token-rotation)
13. [Separate Auth Microservice](#13-microservice-boundary)
14. [Email Delivery: Direct SMTP vs Third-Party API](#14-email-delivery)
15. [ORM & Migrations: SQLAlchemy + Alembic](#15-orm-and-migrations)
16. [Token Transport: httpOnly Cookies vs Headers](#16-token-transport)
17. [Schema Design: Separate users / user_profiles Tables](#17-schema-design)
18. [JSONB Metadata Fields](#18-jsonb-metadata)
19. [Soft-Delete vs Hard Delete](#19-soft-vs-hard-delete)
20. [Dependency Minimalism](#20-dependency-minimalism)

---

## 1. Password Hashing

### Decision: Argon2id

| Option | Pros | Cons |
|--------|------|------|
| **Argon2id** (chosen) | OWASP #1 recommendation; memory-hard (resists GPU/ASIC); won the Password Hashing Competition (2015); configurable memory/time/parallelism | Slightly newer (less battle-tested than bcrypt); `argon2-cffi` is a C extension (needs compilation or binary wheel) |
| **bcrypt** | Battle-tested (25+ years); widely available; simple API; `bcrypt` package has pre-built wheels for all platforms | NOT memory-hard — vulnerable to specialized hardware (FPGAs/ASICs); fixed 72-byte password limit (silently truncates longer passwords) |
| **scrypt** | Memory-hard like Argon2; available in Python stdlib `hashlib` | Harder to tune correctly; less studied than Argon2; not OWASP's first recommendation |

### Why Argon2id wins for Poruta

This is a government-adjacent customs system handling trade data. The threat model includes state-level adversaries and organized crime with significant compute resources. Argon2id's memory-hardness means attackers can't just throw GPUs at stolen hashes — they need proportionally large amounts of RAM per hash attempt, which is orders of magnitude more expensive.

The `argon2-cffi` package provides pre-built wheels for Windows, Linux, and macOS — no compilation needed in practice. The dependency is small (single C library wrapper).

bcrypt would also be acceptable. If the team encounters installation issues with `argon2-cffi` on the target deployment platform, switching to bcrypt is a 5-line code change. The abstraction layer in `core/security.py` isolates this.

### Third-party cost

- **argon2-cffi**: ~50KB, 1 transitive dependency (`cffi`). Minimal.
- Alternative: `bcrypt` package is ~30KB, 0 transitive dependencies. Even smaller.

**Verdict**: Keep Argon2id. The dependency is tiny and the security gain for a customs system is worth it.

---

## 2. JWT Signing

### Decision: HS256 (revised from RS256)

| Option | Pros | Cons |
|--------|------|------|
| **HS256** (revised choice) | Single shared secret; `PyJWT` with zero extras (no `cryptography` package); fast; simple key management | Symmetric — every service that needs to verify tokens must know the secret |
| **RS256** (original plan) | Asymmetric — only auth service holds private key; other services verify with public key (no shared secret); standard for multi-service architectures | Requires `cryptography` package (~3MB compiled); RSA key pair management; slower signing (not meaningful at our scale) |

### Why we revise to HS256

The original plan proposed RS256 for defense-in-depth. But upon analysis:

1. **Poruta has ONE auth service and ONE frontend**. There is no microservice mesh where dozens of services need to independently verify tokens. RS256's value is in multi-service architectures where you don't want to distribute a shared secret.

2. **RS256 requires the `cryptography` package** — a large C-compiled dependency (~3MB) with complex build requirements. This directly contradicts the goal of minimal dependencies.

3. **HS256 with a strong secret (256-bit) is cryptographically sound**. OWASP does not recommend RS256 over HS256 for single-service deployments.

4. **If Poruta grows into a microservice architecture later**, upgrading from HS256 to RS256 is a configuration change (new key, updated `config.py`, reissue tokens). Not a rewrite.

**The tradeoff**: We lose asymmetric verification (other services would need the secret to verify tokens). We gain zero dependency on the `cryptography` package, simpler key management (one env variable instead of key files), and faster token operations.

### Third-party cost

- **HS256 path**: `PyJWT` (~20KB, 0 transitive dependencies). Install: `pip install PyJWT`
- **RS256 path**: `PyJWT[crypto]` or `python-jose[cryptography]` (~3MB, pulls in `cryptography` which has C extensions)

**Verdict**: Switch to HS256. Removes the largest dependency in the stack. Revisit RS256 only if Poruta adds more backend services that need token verification.

---

## 3. Token Lifespans

### Decision: 15-min access token + 7-day refresh token

| Shorter Access (5 min) | 15 min (chosen) | Longer Access (1 hour) |
|-------------------------|------------------|------------------------|
| More secure; smaller window if token is stolen | Balance of security and UX; reasonable for a work-session app | Fewer refresh calls; better UX on slow connections |
| Constant refresh requests; bad UX on slow networks | Standard industry practice (Google, Auth0, Okta all use 5-15 min) | If stolen, attacker has a full hour of access |
| May hit rate limits if frontend implementation is naive | | |

| 1-day refresh | 7-day refresh (chosen) | 30-day refresh |
|---------------|------------------------|----------------|
| User re-logs in daily; annoying for desktop app | One login per week; reasonable for customs officers | One login per month; convenient but risky |
| Tighter control if device is stolen | Balances convenience with security | If device is stolen/lost, attacker has a month |
| | Refresh tokens are rotated and revocable, mitigating theft | |

### Why this balance

Customs agents and inspectors work 8-hour shifts. A 15-minute access token means the frontend silently refreshes ~32 times per shift — invisible to the user. A 7-day refresh means they log in once at the start of the week.

The risk of a 7-day refresh token is mitigated by:
- **Rotation**: Each refresh invalidates the old token and issues new ones. A stolen token becomes detectable (the legitimate user's next refresh will fail with the old token, triggering revocation of the entire token family).
- **DB-stored**: We can revoke any refresh token instantly (e.g., on password change, on admin deactivation).

**No third-party impact**: Token lifespans are pure configuration. No dependency implications.

---

## 4. Token Storage

### Decision: SHA-256 hash all tokens before storing in database

| Store plaintext | SHA-256 hash (chosen) | bcrypt hash tokens |
|-----------------|------------------------|--------------------|
| Simple; direct lookup | Lookup by hash; same speed (indexed) | Very slow lookup; bcrypt is intentionally slow |
| If DB is breached, attacker has all valid tokens | If DB is breached, tokens are useless — can't reverse SHA-256 | Overkill — tokens are random, not user-chosen passwords |
| Equivalent to storing passwords in plaintext | Industry standard (GitHub, Stripe do this) | No benefit over SHA-256 for random tokens |

### Why SHA-256

Tokens are 32+ byte cryptographically random values. Unlike passwords, they have maximum entropy — no dictionary attacks possible. SHA-256 is a one-way function that prevents token recovery from a database dump, but is fast enough for real-time lookups (unlike bcrypt, which would add ~200ms per token verification).

**No third-party impact**: SHA-256 is in Python's stdlib `hashlib`. Zero dependency.

---

## 5. Database Strategy

### Decision: Separate PostgreSQL database (`poruta_auth`) for auth

| Same DB as backend | Separate DB (chosen) | Separate DB server |
|--------------------|----------------------|--------------------|
| One connection string; simpler ops | Two databases, one PostgreSQL server | Two servers; maximum isolation |
| Schema coupling risk; auth tables mixed with business tables | Clean boundary; auth schema can't accidentally join with business tables | Added infrastructure cost and complexity |
| Single point of compromise | Compromise of one DB doesn't give access to the other | | 
| One backup strategy | Slightly more complex backup, but same server | |

### Why separate database, same server

Auth data (passwords, tokens, sessions) has different security requirements than business data (declarations, HS codes, shipment documents). A separate database means:

- A SQL injection in the business API cannot access auth tables (different database, different connection string, different credentials)
- Auth migrations are independent — we never accidentally break business tables
- Can apply different backup/retention policies (auth logs may have different compliance requirements)

We use the **same PostgreSQL server** to avoid operational overhead. The user already has PostgreSQL for the backend. No new infrastructure needed.

**Third-party impact**: Zero. Same PostgreSQL server, just a second database. One `CREATE DATABASE poruta_auth;` command.

---

## 6. Framework

### Decision: FastAPI

This was the user's explicit requirement. But let's validate:

| FastAPI (chosen) | Flask | Django |
|------------------|-------|--------|
| Async-native; great for I/O-bound auth operations | Synchronous (extensions exist for async); simpler | Batteries-included but heavy; built-in auth system |
| Auto-generated OpenAPI docs (free Swagger UI) | Manual API docs | Django REST Framework adds docs |
| Type-safe with Pydantic (request validation is automatic) | Manual validation or use marshmallow | Serializers add validation |
| Dependency injection system (perfect for `get_current_user`) | DIY or use Flask-Injector | Middleware/decorators for auth |
| ~10x faster than Flask for concurrent requests | Sufficient for auth loads; auth isn't CPU-bound | Sufficient for auth loads |

### Why FastAPI is correct here

Auth is I/O-bound (database queries, SMTP sends, token operations). FastAPI's async-native design means a single process handles many concurrent auth requests without blocking. The auto-generated OpenAPI documentation is also valuable for the frontend team — they get a live, interactive API reference for free.

**Third-party impact**: `fastapi` + `uvicorn` are the base. `pydantic` comes with FastAPI. Total: 3 packages + their transitive deps (all lightweight).

---

## 7. Async Architecture

### Decision: Async everything (asyncpg, aiosmtplib, async SQLAlchemy)

| Sync (simpler) | Async (chosen) |
|-----------------|----------------|
| Easier to debug; no `async/await` throughout | Non-blocking I/O; single process handles 100+ concurrent requests |
| `psycopg2` is thoroughly battle-tested | `asyncpg` is 3x faster than `psycopg2` for queries |
| `smtplib` is in the stdlib (zero-dependency) | `aiosmtplib` is a separate package but doesn't block the event loop when sending email |
| Thread-pool for concurrency (GIL limits CPU, not I/O) | True concurrency without thread overhead |

### The honest tradeoff

For an auth service with moderate load (hundreds of users, not millions), sync would work perfectly fine. Authentication endpoints are called infrequently per user (login once per session, refresh every 15 minutes). The performance difference between sync and async is irrelevant at this scale.

**However**, since we're already using FastAPI (which is async-native), mixing sync database calls would require wrapping them in `run_in_executor()` or using FastAPI's automatic threadpool conversion. This adds complexity rather than reducing it. Going fully async is actually simpler within FastAPI's paradigm.

### Third-party impact

- **asyncpg**: Replaces `psycopg2`. Same dependency count (1 package). `asyncpg` is maintained by the same team as `uvloop` — highly reliable.
- **aiosmtplib**: ~30KB package. Alternative: use stdlib `smtplib` in a thread executor (`loop.run_in_executor(None, send_sync_email)`). This would eliminate one dependency at the cost of slightly more code in `email_service.py`.

**Verdict**: Keep async. Within the FastAPI ecosystem, it's actually the path of least resistance. Could drop `aiosmtplib` and use stdlib `smtplib` in executor if we want to eliminate one more dependency (discussed in section 20).

---

## 8. Email Verification

### Decision: Required for all users before platform access

| No verification | Optional | Required for all (chosen) |
|-----------------|----------|---------------------------|
| Fastest onboarding; zero friction | Users can skip; mix of verified and unverified | Users must check email before proceeding |
| Anyone can sign up with fake emails; spam accounts | Hard to enforce later; "optional" often means "never" | Proves email ownership; enables password recovery |
| No way to send password reset emails to unverified addresses | | Adds one extra step to onboarding |
| | | Invited users skip this (already verified by trust chain) |

### Why required

If a user signs up with a fake email:
1. They can never recover their password
2. We can't send them important notifications (declaration status changes, payment confirmations)
3. The audit log has meaningless email addresses
4. For a government customs platform, user identity matters

**The nuance**: Invited users (agents, inspectors, government) skip email verification because the invitation flow already proves the email is valid — the inviter typed it, and only someone with access to that inbox can click the invitation link.

**Third-party impact**: Requires email sending capability (SMTP). This is already needed for invitation emails and password resets, so email verification adds no new dependencies.

---

## 9. Invitation-Based Registration

### Decision: Restricted roles can only register via invitation link

| Self-signup for all roles (with approval) | Invitation only (chosen) | Manual account creation by admin |
|-------------------------------------------|--------------------------|----------------------------------|
| Lower barrier; users request access | Only invited people can create accounts | Admin creates accounts including passwords |
| Requires approval workflow (pending state, admin review) | No orphan accounts; every restricted user has a sponsor | Admin knows everyone's initial password (security issue) |
| Risk: spam registrations for agent/inspector roles | Invitation tokens are single-use, expire in 24h | Doesn't scale; admin bottleneck |
| Additional states to manage: pending, approved, rejected | Clean: you either have a valid token or you don't | No self-service; bad UX |

### Why invitation-only

The invitation model creates a **trust chain**:
- Admin creates Government accounts → Government validity is traceable to Admin
- Government invites Inspectors → Inspector validity is traceable to Government
- Agency Manager invites Agents → Agent validity is traceable to their manager

This is critical for a customs/government system. If an unauthorized inspector appears in the system, you can immediately trace: who invited them, when, from what IP address. The audit trail is built into the registration model.

The "self-signup with approval" approach was a contender, but it requires building an admin approval queue, notification system for pending registrations, and handling the edge case where someone's registration sits in "pending" for days. The invitation model avoids all of this — if you have a token, you're already approved.

**Third-party impact**: None. Invitation tokens are generated with Python's `secrets.token_urlsafe()` (stdlib) and hashed with `hashlib.sha256()` (stdlib).

---

## 10. Admin Creation

### Decision: CLI command + env-var auto-seed hybrid

| CLI only | Env-var auto-seed only | Hybrid (chosen) | Web-based first-run wizard |
|----------|------------------------|------------------|---------------------------|
| Explicit, auditable, intentional | Good for CI/CD and Docker | Both benefits combined | Nice UX but security risk (race condition: who hits /setup first?) |
| Requires terminal access to server | Risk: env var left in `.env` file permanently | CLI for production; env-var for development/CI | Exposes admin creation endpoint to the internet |
| Not automatable in CI/CD | Admin password in environment (visible in process list) | | Must be disabled after first run (complexity) |

### Why hybrid

- **Development/Docker**: Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env.example`. On first `docker-compose up`, the admin account exists automatically. Quick to start developing.
- **Production**: Use the CLI command explicitly. The admin who runs it knows exactly what they're doing. The command is logged.
- **Safety**: The auto-seed only runs if no admin account exists yet. Once an admin is created (by either method), the env-var seed is a no-op.

**Third-party impact**: Zero. It's just Python code with `argparse` or `click`. We can even use `argparse` from stdlib to avoid adding `click`/`typer`.

---

## 11. Brute-Force Protection

### Decision: Per-email account lockout (5 attempts → 15 min lock)

| No protection | IP-based rate limiting | Per-email lockout (chosen) | CAPTCHA after N attempts |
|---------------|------------------------|----------------------------|--------------------------|
| Trivial brute force | Blocks entire IP; unfair to shared networks (offices, NAT) | Locks only the targeted account | Adds CAPTCHA dependency (reCAPTCHA/hCaptcha) |
| | Easily bypassed with rotating IPs | Attacker can lock out legitimate users (DoS) | Requires frontend integration |
| | | Mitigated: 15-min lockout is temporary; monitor in logs | External service dependency |
| | | | Third-party JavaScript on your login page |

### The honest downside: account lockout DoS

An attacker who knows a user's email can intentionally lock their account by sending 5 bad passwords. This is a known weakness of account lockout.

**Mitigations**:
1. The lockout is temporary (15 min, not permanent)
2. The auth log records every failed attempt with IP + user agent — we can detect automated lockout attacks
3. Admins can manually unlock accounts via the admin panel
4. In a future iteration, adding CAPTCHA after 3 failed attempts (before lockout) would eliminate this entirely

We chose lockout over CAPTCHA because CAPTCHA requires a third-party service (Google reCAPTCHA, hCaptcha), adds JavaScript to the login page, and impacts UX. For a system primarily used by customs professionals at known workstations, account lockout is proportionate.

**Third-party impact**: Zero. Pure database logic (increment counter, set `locked_until` timestamp).

---

## 12. Refresh Token Rotation

### Decision: Every refresh request issues a new token pair and invalidates the old refresh token

| No rotation (static refresh token) | Rotation (chosen) | Rotation + token family tracking |
|------------------------------------|---------------------|----------------------------------|
| Simpler; one refresh token for 7 days | Old token invalidated on each refresh | If reuse detected, revoke entire family |
| If stolen, attacker has 7-day access | Stolen token becomes obvious (legitimate user's next refresh fails) | Maximum security but significant complexity |
| | One DB update per refresh | Requires tracking parent-child token relationships |

### Why rotation without full family tracking (initially)

Full token family tracking (where reuse of an old token triggers revocation of all tokens in the chain) is the gold standard — but it adds significant schema complexity (parent_token_id, token_family_id columns, recursive revocation logic). For v1, simple rotation provides 90% of the security benefit:

1. Attacker steals refresh token
2. Attacker uses it → gets new pair (old token invalidated)
3. Legitimate user's next refresh fails (old token is gone)
4. User re-logs in → attacker's tokens are now the "old chain" and will eventually expire

The gap: between steps 2 and 3, the attacker has valid tokens and the user doesn't. With family tracking, step 2 would invalidate the attacker's new tokens too. We can add this in a future iteration — the schema change is additive (one column + one query).

**Third-party impact**: Zero. Pure database logic.

---

## 13. Microservice Boundary

### Decision: auth_services as a separate service from poruta-backend

| All-in-one (auth inside poruta-backend) | Separate service (chosen) | Separate service + API gateway |
|-----------------------------------------|---------------------------|-------------------------------|
| Simpler deployment; one process | Independent deployment; auth can scale independently | Full microservice architecture with gateway routing |
| Shared database connection; direct function calls | Clear ownership boundary; auth team can work independently | Maximum flexibility but significant ops overhead |
| If backend goes down, auth goes down | Auth can stay up even if ML/OCR backend has issues | Requires running an API gateway (nginx, Kong, Traefik) |
| One codebase to maintain | Two codebases; inter-service communication overhead | Three+ components to deploy and monitor |

### Why separate

poruta-backend is an ML/OCR service with heavy dependencies (PyTorch, PaddlePaddle, CUDA). It processes documents, runs inference, and handles triton server communication. Auth has nothing to do with any of that. Bundling them together means:

1. Every auth deployment requires reinstalling the ML stack
2. A crash in the OCR pipeline takes down authentication
3. The auth service can't be lightweight

The separate service means auth_services is a ~5MB Docker image (Python + FastAPI + asyncpg + argon2). poruta-backend is a ~10GB image (CUDA + PyTorch). Different scaling profiles, different failure domains.

**Third-party impact**: The frontend needs to know the auth service URL (one env variable: `NEXT_PUBLIC_AUTH_URL`). No API gateway needed — the frontend talks directly to auth_services on port 5000 and poruta-backend on port 8000.

---

## 14. Email Delivery

### Decision: Direct SMTP via Zoho Mail

| SMTP direct (chosen) | SendGrid API | AWS SES | Console logging (dev only) |
|-----------------------|-------------|---------|---------------------------|
| Zero third-party API; you own the mail server (Zoho) | Reliable delivery; analytics; bounce handling | Cheapest at scale; enterprise-grade | Zero email dependency; just for development |
| Deliverability depends on Zoho's reputation (good) | $15/mo for 50K emails; another vendor to manage | AWS account required; IAM configuration | Can't test real email flows |
| No analytics (open rates, bounces) | API key management | Region-locked; compliance considerations | |
| Max ~500 emails/day on Zoho free tier | | | |
| Already configured with poruta.com domain + Cloudflare DNS | | | |

### Why direct SMTP

You already have `noreply@poruta.com` on Zoho with DNS records on Cloudflare. This means:
- SPF, DKIM, DMARC are (or can be) configured → good deliverability
- No new vendor accounts to create
- No API keys from a third-party service to manage
- No monthly costs beyond what you already pay for Zoho

The auth service sends low-volume transactional emails: verification (once per user), invitations (infrequent), password resets (rare). Even on Zoho's basic plan, this is well within limits.

### Third-party impact

- **aiosmtplib**: One package (~30KB) for async SMTP. Alternative: use Python stdlib `smtplib` inside `asyncio.to_thread()` — this eliminates the dependency entirely with ~3 extra lines of code. Both approaches work.

**Verdict**: Start with `aiosmtplib` for clean async code. If we want to eliminate it later, wrapping stdlib `smtplib` is a trivial change.

---

## 15. ORM & Migrations

### Decision: SQLAlchemy (async) + Alembic

| Raw SQL (asyncpg directly) | SQLAlchemy + Alembic (chosen) | Tortoise ORM | SQLModel |
|---------------------------|-------------------------------|-------------|----------|
| Zero ORM abstraction; full control | Industry standard; type-safe models; auto-migrations | Async-native ORM; Django-like syntax | SQLAlchemy + Pydantic fusion by FastAPI creator |
| Must write all SQL by hand; migration scripts by hand | Alembic adds a dependency but handles migration diffs | Less mature; smaller community | Newer; less documentation; some edge cases |
| No model layer for Pydantic schema generation | Rich ecosystem; well-documented | Not compatible with existing SQLAlchemy tooling | Breaks for some advanced SQLAlchemy patterns |
| Fastest raw performance | Slight ORM overhead (negligible for auth loads) | | |

### Why SQLAlchemy

Auth services have complex relationships (users → profiles, users → agencies, users → tokens). Writing and maintaining raw SQL JOINs, INSERT/UPDATE statements, and migration scripts by hand is error-prone. SQLAlchemy gives us:

1. **Model definitions** that double as documentation (read the model, understand the schema)
2. **Relationship loading** (user.profile, user.agencies) without manual JOINs
3. **Alembic auto-detection** of schema changes (add a column to a model, run `alembic revision --autogenerate`, done)
4. **Type hints** that Pydantic can consume for automatic request/response validation

### Could we go simpler?

Yes — for 9 tables with known, stable schemas, raw asyncpg would work. But the time saved by Alembic's auto-migrations and SQLAlchemy's relationship management outweighs the dependency cost. And if you ever need to add a column (e.g., `mfa_secret` to users), Alembic makes it a one-command operation.

**Third-party impact**: `sqlalchemy[asyncio]` + `asyncpg` + `alembic` = 3 packages. These would be needed regardless of the ORM choice (even raw SQL needs `asyncpg`). Alembic is the only "extra" — and it replaces manually writing `ALTER TABLE` SQL scripts.

---

## 16. Token Transport

### Decision: httpOnly cookie for refresh token, Authorization header for access token

| localStorage for both | httpOnly cookie for both | Cookie for refresh + header for access (chosen) |
|-----------------------|--------------------------|--------------------------------------------------|
| Simple; frontend controls everything | Most secure; immune to XSS for both tokens | Refresh immune to XSS; access available for API calls |
| XSS vulnerability: any injected script steals both tokens | CSRF vulnerability: browser auto-sends cookies on requests | Balance: most sensitive token (refresh) is protected |
| | Need CSRF tokens or SameSite=Strict | Access token in-memory (not localStorage) — XSS can't steal it if it's not persisted |
| | Can't easily use access token for non-browser API clients | Access token short-lived (15 min) even if somehow stolen |

### Why this hybrid

The refresh token is the crown jewel — it can create new access tokens for 7 days. It MUST be in an httpOnly cookie (JavaScript cannot read it → XSS cannot steal it). With `SameSite=Strict`, browsers only send it on same-site requests → CSRF is also mitigated.

The access token needs to be in the `Authorization` header for API calls — this is how FastAPI's dependency injection reads it. Storing it in memory (JavaScript variable, not localStorage or sessionStorage) means it only exists during the page session and is not accessible to injected scripts that scan storage.

**Third-party impact**: None. This is a frontend implementation decision. The auth service just sets a `Set-Cookie` header on login/refresh.

---

## 17. Schema Design

### Decision: Separate `users` and `user_profiles` tables

| Single `users` table | Separate tables (chosen) | One table per role |
|----------------------|--------------------------|---------------------|
| Simpler queries; one JOIN fewer | Clean separation: auth data vs. personal data | Maximum flexibility per role |
| Many nullable columns (company_name only for importers, etc.) | Auth-related queries don't load personal information | Massive duplication; different schemas to maintain |
| Mixing auth concerns with profile concerns | Profile can be extended without touching auth schema | 6 tables instead of 2 |
| | JSONB metadata handles role-specific fields | |

### Why separate

The `users` table is referenced by 5 other tables (tokens, logs, agencies). Keeping it lean (email, password_hash, role, flags) means those foreign key lookups are fast. Profile information (name, phone, company, etc.) is only needed when displaying user details — not during authentication.

This separation also means:
- The auth log writes to `auth_logs` referencing `users.id` without loading any personal data
- Profile completion is a separate concern from account creation
- GDPR/data deletion: you could theoretically wipe personal data from profiles while keeping the auth record for audit purposes

**Third-party impact**: None. Pure schema design.

---

## 18. JSONB Metadata

### Decision: JSONB column on `user_profiles` for role-specific fields

| Extra columns for each role's fields | JSONB metadata (chosen) | Separate profile tables per role |
|--------------------------------------|-------------------------|----------------------------------|
| Type-safe at DB level; DB can enforce constraints | Flexible; add fields without migrations | Maximum type safety |
| Many nullable columns; sparse table | No DB-level type enforcement; validated in application layer | 6 extra tables |
| Every new field requires a migration | New fields added by updating Pydantic schema only | Complex queries across roles |

### What goes in JSONB vs. dedicated columns

- **Dedicated columns**: first_name, last_name, phone, company_name, avatar_url — these are common across roles or critical for queries
- **JSONB metadata**: role-specific fields like importer's TIN number, agency manager's certification, inspector's badge number — these vary by role and are rarely queried directly

This avoids the "kitchen sink" table with 30 nullable columns while keeping the most queried fields in proper columns (indexable, type-safe).

**Third-party impact**: None. PostgreSQL JSONB is a native type. No extension needed.

---

## 19. Soft-Delete vs Hard Delete

### Decision: Soft-delete via `is_active` flag

| Hard delete | Soft-delete (chosen) | Soft-delete + archival |
|-------------|----------------------|------------------------|
| Simple; row is gone | Row remains with `is_active=false` | Move to archive table after N days |
| Foreign key issues (auth_logs reference deleted users) | No FK violations; audit trail preserved | Most thorough but adds complexity |
| Compliance risk: you may need records for audits | Compliance-friendly: records exist but account is disabled | |
| Cannot undo | Reversible: set `is_active=true` to reactivate | |

### Why soft-delete

In a government customs system, you cannot delete a user who processed 500 declarations, inspected 200 shipments, and generated revenue reports. Those records reference the user's ID. Hard-deleting the user either:
1. Cascades and deletes all their work (catastrophic)
2. Sets FKs to null (loses the audit trail: "who processed this declaration?")
3. Fails due to FK constraints (frustrating)

Soft-delete means deactivated users can't log in, their refresh tokens are revoked, but all historical references to their account remain intact. An admin can reactivate them if needed.

**Third-party impact**: None. One boolean column.

---

## 20. Dependency Minimalism

### Full dependency audit

Here is every Python package the auth service will use, categorized by necessity:

#### Absolutely Required (5 packages)

| Package | Purpose | Size | Can we replace it? |
|---------|---------|------|---------------------|
| `fastapi` | Web framework | ~300KB | No — user's explicit choice |
| `uvicorn` | ASGI server | ~200KB | Could use `hypercorn` or `daphne`, but uvicorn is FastAPI's default |
| `pydantic` | Data validation | Bundled with FastAPI | No — core to FastAPI's design |
| `sqlalchemy` | ORM + query builder | ~2MB | Could use raw `asyncpg` — tradeoff discussed in section 15 |
| `asyncpg` | PostgreSQL driver | ~700KB | No — required to talk to PostgreSQL |

#### Strongly Recommended (4 packages)

| Package | Purpose | Size | Alternative |
|---------|---------|------|-------------|
| `argon2-cffi` | Password hashing | ~50KB | `bcrypt` (~30KB) — slightly less secure but still excellent |
| `PyJWT` | JWT creation/verification | ~20KB | Manual JWT implementation — not recommended (security risk) |
| `alembic` | Database migrations | ~600KB | Hand-written SQL migration files — error-prone |
| `pydantic-settings` | Environment variable management | ~50KB | `os.environ` + manual parsing — more code but zero dependency |

#### Optional (can be eliminated)

| Package | Purpose | Size | Alternative | Tradeoff |
|---------|---------|------|-------------|----------|
| `aiosmtplib` | Async SMTP | ~30KB | `smtplib` (stdlib) in `asyncio.to_thread()` | 3 extra lines of wrapper code |
| `jinja2` | Email templates | ~500KB | Python f-strings | Less maintainable templates; HTML in Python strings |
| `python-multipart` | Form data parsing | ~20KB | Only needed if accepting `application/x-www-form-urlencoded` — JSON body doesn't need it |

### Minimal viable dependency list

If we aggressively minimize:

```
# Required
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
alembic

# Security (cannot safely DIY)
argon2-cffi
PyJWT

# Optional but recommended
pydantic-settings
```

**Total: 8 packages** (7 required + 1 recommended). Everything else can be replaced with stdlib.

- Drop `aiosmtplib` → use `smtplib` + `asyncio.to_thread()`
- Drop `jinja2` → use f-strings for email templates
- Drop `python-multipart` → accept JSON bodies only (no form data)
- Drop `pydantic-settings` → use `os.environ.get()` with manual defaults (but pydantic-settings is tiny and gives validation)

**Recommendation**: Use the 8-package list. This is genuinely minimal for a production auth service. Anything less means reimplementing crypto in application code (dangerous) or managing SQL migrations by hand (tedious).

---

## Summary: Decision Matrix

| # | Decision | Alternatives Considered | Key Tradeoff | Third-Party Cost |
|---|----------|------------------------|--------------|------------------|
| 1 | Argon2id | bcrypt, scrypt | Maximum security vs. slightly larger package | 1 package (50KB) |
| 2 | HS256 JWT | RS256 | Simplicity + zero deps vs. asymmetric verification | 1 package (20KB) |
| 3 | 15-min / 7-day tokens | Various lifespans | UX convenience vs. exposure window | None |
| 4 | SHA-256 token hashing | Plaintext, bcrypt | Security vs. lookup simplicity (no real tradeoff) | None (stdlib) |
| 5 | Separate auth DB | Same DB, separate server | Isolation vs. operational simplicity | None |
| 6 | FastAPI | Flask, Django | Async + auto docs vs. simplicity | 3 packages (base) |
| 7 | Async everywhere | Sync with threads | Consistency with FastAPI vs. simpler debugging | 0-1 package |
| 8 | Email verification | None, optional | Security + identity vs. onboarding friction | None (uses existing SMTP) |
| 9 | Invitation-based | Self-signup + approval | Trust chain + audit trail vs. lower barrier | None (stdlib tokens) |
| 10 | CLI + env-var admin | CLI only, web wizard | Flexibility vs. slight complexity | None |
| 11 | Account lockout | IP rate limit, CAPTCHA | No external deps vs. lockout DoS risk | None |
| 12 | Token rotation | Static tokens, family tracking | Simple security vs. maximum security | None |
| 13 | Separate microservice | Monolith | Independence vs. inter-service complexity | None |
| 14 | Direct SMTP (Zoho) | SendGrid, SES | Zero vendor vs. deliverability analytics | 0-1 package |
| 15 | SQLAlchemy + Alembic | Raw SQL, Tortoise | Productivity vs. abstraction overhead | 2 packages |
| 16 | Cookie + header | localStorage, all cookies | XSS protection vs. implementation complexity | None |
| 17 | Split users/profiles | Single table | Clean separation vs. one more JOIN | None |
| 18 | JSONB metadata | Extra columns, per-role tables | Flexibility vs. type safety at DB level | None |
| 19 | Soft-delete | Hard delete | Audit compliance vs. data accumulation | None |
| 20 | 8 packages total | — | Minimal viable stack | 8 Python packages |

---

## What This Plan Does NOT Include (and Why)

| Feature | Why excluded | When to add |
|---------|-------------|-------------|
| MFA/2FA | User deferred; architecture supports it (add `mfa_enabled`, `mfa_secret` columns) | When handling sensitive financial operations |
| OAuth/Social Login | User deferred; add `oauth_provider`, `oauth_id` columns later | When user base grows beyond institutional users |
| CAPTCHA | Adds third-party JS; account lockout is sufficient for institutional use | If automated lockout attacks become a problem |
| API Gateway | One frontend + one auth service; direct communication is simpler | When adding more microservices |
| Redis for sessions | JWT is stateless; refresh tokens in PostgreSQL are sufficient | When handling 10K+ concurrent sessions |
| Webhook notifications | Auth events are internal; no external consumers yet | When other services need to react to auth events |
| IP whitelisting | Customs officers may work from various locations | When deploying behind a VPN |

---

## Revised Architecture Decision (Post-Analysis)

Based on the tradeoff analysis, one change from the original plan:

| Original | Revised | Reason |
|----------|---------|--------|
| RS256 JWT (python-jose + cryptography) | **HS256 JWT (PyJWT only)** | Eliminates ~3MB `cryptography` package; single-service architecture doesn't benefit from asymmetric signing; can upgrade later |

All other decisions stand after analysis. The total dependency count is **8 Python packages** — genuinely minimal for a production auth service with password hashing, JWT, PostgreSQL ORM, and migrations.
