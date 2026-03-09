# Step 03 — Core Security Module

> **Phase**: A (Foundation)  
> **Dependencies**: Step 01 (config)  
> **Parallel with**: Step 02 (database)  
> **Produces**: Password hashing, JWT operations, token utilities, FastAPI auth dependencies

---

## Objective

Build the security layer that all auth endpoints depend on: Argon2id password hashing, HS256 JWT creation/validation, cryptographically secure token generation with SHA-256 hashing for storage, and FastAPI dependency injection for route protection.

---

## Files to Create

```
auth_services/src/core/
├── __init__.py
├── security.py          # Password hashing, JWT, token utilities
├── dependencies.py      # FastAPI deps (get_current_user, require_role)
└── exceptions.py        # Custom HTTP exceptions
```

---

## security.py — Functions

### Password Hashing (Argon2id)

```python
def hash_password(password: str) -> str:
    """Hash password with Argon2id. Returns PHC-format hash string."""
    # argon2-cffi handles salt generation, encoding, and parameter embedding
    # Default params: time_cost=3, memory_cost=65536 (64MB), parallelism=4

def verify_password(password: str, hash: str) -> bool:
    """Verify password against Argon2id hash. Returns True if match."""
    # Also handles rehashing check (if params have changed)
```

### JWT (HS256)

```python
def create_access_token(user_id: str, role: str, email: str) -> str:
    """Create short-lived access token (15 min).
    Payload: sub=user_id, role=role, email=email, type=access, exp, iat, jti
    """

def create_refresh_token(user_id: str) -> str:
    """Create long-lived refresh token (7 days).
    Payload: sub=user_id, type=refresh, exp, iat, jti
    """

def decode_token(token: str) -> dict:
    """Decode and validate JWT. Raises exception if expired/invalid.
    Returns payload dict.
    """
```

**JWT payload structure (access token):**
```json
{
  "sub": "user-uuid",
  "role": "importer",
  "email": "user@example.com",
  "type": "access",
  "exp": 1709913600,
  "iat": 1709912700,
  "jti": "unique-token-id"
}
```

### Token Utilities

```python
def generate_token() -> str:
    """Generate 32-byte URL-safe random token using secrets.token_urlsafe(32)."""

def hash_token(token: str) -> str:
    """SHA-256 hash a token for database storage. Returns hex digest."""
```

### Password Validation

```python
def validate_password_strength(password: str) -> list[str]:
    """Check password against policy. Returns list of violations (empty = valid).
    Rules:
    - Minimum 12 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - At least 1 special character (!@#$%^&*...)
    """
```

---

## dependencies.py — FastAPI Dependencies

### get_current_user

```python
async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Extract and validate access token from Authorization header.
    
    1. Parse "Bearer <token>" from header
    2. Decode JWT (validates signature + expiry)
    3. Check token type is "access"
    4. Lookup user by ID from token's "sub" claim
    5. Verify user is_active=True
    6. Return User ORM object
    
    Raises 401 if token is invalid, expired, or user not found/inactive.
    """
```

### require_role

```python
def require_role(*roles: str):
    """Factory that returns a FastAPI dependency checking the user's role.
    
    Usage in routes:
        @router.post("/invite", dependencies=[Depends(require_role("agency_manager", "government", "admin"))])
        async def send_invite(current_user: User = Depends(get_current_user)):
            ...
    
    Raises 403 if user's role not in allowed roles.
    """
```

### get_current_verified_user

```python
async def get_current_verified_user(
    user: User = Depends(get_current_user)
) -> User:
    """Same as get_current_user but also requires is_email_verified=True.
    Raises 403 with message "Email not verified" if not verified.
    """
```

### get_current_complete_user

```python
async def get_current_complete_user(
    user: User = Depends(get_current_verified_user)
) -> User:
    """Requires email verified AND profile_completed=True.
    Most endpoints will use this — only profile completion endpoint uses get_current_verified_user.
    """
```

---

## exceptions.py — Custom Exceptions

```python
class AuthenticationError(Exception):
    """401 — Invalid credentials, expired token, etc."""
    
class AuthorizationError(Exception):
    """403 — Insufficient permissions."""
    
class ValidationError(Exception):
    """422 — Invalid input (password too weak, invalid email, etc.)"""
    
class ConflictError(Exception):
    """409 — Email already registered, etc."""
    
class NotFoundError(Exception):
    """404 — User/agency/token not found."""
    
class RateLimitError(Exception):
    """429 — Account locked due to too many failed attempts."""
```

These are caught by global exception handlers in `main.py` and converted to appropriate HTTP responses with structured error bodies:

```json
{
  "error": "authentication_error",
  "message": "Invalid email or password",
  "details": null
}
```

---

## Security Considerations

1. **Timing attacks**: `verify_password` uses Argon2's constant-time comparison. No early exit.
2. **JWT secret rotation**: If `JWT_SECRET_KEY` changes, all existing tokens become invalid. Users must re-login. This is a feature, not a bug (emergency revocation).
3. **Token JTI**: Each token gets a unique `jti` (JWT ID) — enables individual token revocation if needed in the future.
4. **No token type confusion**: Access tokens have `type: "access"`, refresh tokens have `type: "refresh"`. A refresh token cannot be used as an access token and vice versa.

---

## Acceptance Criteria

- [ ] `hash_password("test123")` returns a valid Argon2id PHC string
- [ ] `verify_password("test123", hash)` returns True for matching password
- [ ] `verify_password("wrong", hash)` returns False
- [ ] `create_access_token()` produces a valid JWT decodable by `decode_token()`
- [ ] `decode_token()` raises error for expired tokens
- [ ] `decode_token()` raises error for tokens with wrong signature
- [ ] `validate_password_strength("weak")` returns violation list
- [ ] `validate_password_strength("Str0ng!P@ssw0rd")` returns empty list
- [ ] `get_current_user` dependency rejects requests without Authorization header
- [ ] `require_role("admin")` rejects non-admin users with 403
- [ ] `generate_token()` produces URL-safe strings
- [ ] `hash_token(token)` produces consistent SHA-256 hex digests
