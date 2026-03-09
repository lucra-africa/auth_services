# Step 06 — Login & JWT Token Management

> **Phase**: B (Core Auth)  
> **Dependencies**: Steps 02 (models), 03 (security)  
> **Parallel with**: Steps 04-05  
> **Produces**: Login, refresh, logout endpoints

---

## Objective

Authenticate users with email + password, issue JWT token pairs (access + refresh), support token rotation on refresh, and handle logout by revoking refresh tokens. Enforce account lockout after 5 failed attempts.

---

## Endpoints

### POST /auth/login

#### Request
```json
{
  "email": "user@example.com",
  "password": "Str0ng!P@ssw0rd"
}
```

#### Validation & Business Logic

```
1. Look up user by email
   - Not found → log FAILED_LOGIN (user_id=null, email=input), return 401
   - Note: same error message for "email not found" and "wrong password" (prevent enumeration)

2. Check is_active
   - False → return 401 "Account has been deactivated. Contact support."

3. Check lockout
   - If locked_until > now → return 429 "Account locked. Try again in X minutes."
   - If locked_until <= now → reset: failed_login_count=0, locked_until=null

4. Verify password (Argon2id)
   - Wrong password:
     a. Increment failed_login_count
     b. Log FAILED_LOGIN (user_id, email, ip, metadata: {attempt: count})
     c. If failed_login_count >= 5:
        - Set locked_until = now + 15 minutes
        - Log ACCOUNT_LOCKED
        - Return 429 "Account locked due to too many failed attempts. Try again in 15 minutes."
     d. Return 401 "Invalid email or password"

5. Check is_email_verified
   - False → return 403 "Please verify your email address before logging in."

6. Success path:
   a. Reset failed_login_count = 0, locked_until = null
   b. Update last_login_at = now
   c. Create access token (15 min)
   d. Create refresh token (7 days)
   e. Hash refresh token, store in refresh_tokens table (user_id, token_hash, ip, device_info, expires_at)
   f. Log LOGIN action
   g. Return token response
```

#### Response (200)
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "importer",
    "is_email_verified": true,
    "profile_completed": true,
    "profile": {
      "first_name": "Jean-Pierre",
      "last_name": "Habimana",
      "phone": "+250788123456",
      "company_name": "Kigali Electronics Ltd"
    }
  }
}
```

The `user` object in the response allows the frontend to immediately populate the auth store without an additional API call.

#### Error Responses
| Code | Condition | Body |
|------|-----------|------|
| 401 | Wrong email or password | `{"error": "authentication_error", "message": "Invalid email or password"}` |
| 401 | Account deactivated | `{"error": "account_deactivated", "message": "Account has been deactivated. Contact support."}` |
| 403 | Email not verified | `{"error": "email_not_verified", "message": "Please verify your email address before logging in."}` |
| 429 | Account locked | `{"error": "account_locked", "message": "Account locked due to too many failed attempts. Try again in 15 minutes."}` |

---

### POST /auth/refresh

#### Request
```json
{
  "refresh_token": "eyJ..."
}
```

#### Business Logic

```
1. Decode refresh token JWT
   - Invalid/expired → return 401

2. Verify token type is "refresh"
   - Not refresh → return 401

3. Hash the token, look up in refresh_tokens table
   - Not found → return 401 (token was revoked or never existed)
   - Found but revoked_at is set → return 401 "Token has been revoked"
   - Found but expires_at <= now → return 401

4. Load user by ID from token's "sub"
   - User not found or is_active=false → return 401

5. Rotation:
   a. Revoke old refresh token: set revoked_at = now
   b. Create new access token (15 min)
   c. Create new refresh token (7 days)
   d. Hash new refresh token, store in refresh_tokens
   e. Log TOKEN_REFRESH action

6. Return new token pair
```

#### Response (200)
```json
{
  "access_token": "eyJ...(new)",
  "refresh_token": "eyJ...(new)",
  "token_type": "Bearer",
  "expires_in": 900
}
```

---

### POST /auth/logout

#### Request
Requires Authorization header with valid access token.

```json
{
  "refresh_token": "eyJ..."
}
```

#### Business Logic

```
1. Get current user from access token (via dependency)
2. Hash the provided refresh token
3. Look up in refresh_tokens table
4. If found and belongs to current user:
   - Set revoked_at = now
5. Log LOGOUT action
6. Return success (always 200, even if refresh token wasn't found — idempotent)
```

#### Response (200)
```json
{
  "message": "Logged out successfully"
}
```

---

## Refresh Token Cookie (Set-Cookie Header)

On login and refresh, the server sets the refresh token as an httpOnly cookie:

```
Set-Cookie: poruta_refresh_token=eyJ...; HttpOnly; Secure; SameSite=Strict; Path=/auth/refresh; Max-Age=604800
```

- **HttpOnly**: JavaScript cannot read it (XSS protection)
- **Secure**: Only sent over HTTPS (skip in development)
- **SameSite=Strict**: Not sent on cross-site requests (CSRF protection)
- **Path=/auth/refresh**: Only sent to the refresh endpoint (not every request)
- **Max-Age=604800**: 7 days in seconds

The frontend can also accept the refresh token from the JSON response body for native mobile clients or non-browser environments. The cookie is the recommended approach for web browsers.

---

## Account Lockout Timeline

```
Attempt 1: failed → failed_login_count=1
Attempt 2: failed → failed_login_count=2
Attempt 3: failed → failed_login_count=3
Attempt 4: failed → failed_login_count=4
Attempt 5: failed → failed_login_count=5 → LOCKED for 15 minutes
                     locked_until = now + 15 min
                     ACCOUNT_LOCKED logged

(within 15 min)
Attempt 6: → 429 "Account locked. Try again in X minutes."

(after 15 min)
Attempt 7: lockout expired → reset count → normal login flow
```

---

## Acceptance Criteria

- [ ] Valid credentials return 200 with access + refresh tokens
- [ ] Invalid credentials return 401 (same message for wrong email and wrong password)
- [ ] Unverified email returns 403 with "verify email" message
- [ ] Deactivated account returns 401 with "deactivated" message
- [ ] 5 failed attempts lock account for 15 minutes
- [ ] Locked account returns 429 with remaining lockout time
- [ ] Lockout resets after 15 minutes
- [ ] Refresh with valid token returns new token pair
- [ ] Refresh with revoked token returns 401
- [ ] Refresh revokes old token (rotation)
- [ ] Logout revokes refresh token
- [ ] Refresh token is set as httpOnly cookie on login
- [ ] LOGIN, FAILED_LOGIN, TOKEN_REFRESH, LOGOUT, ACCOUNT_LOCKED actions logged
- [ ] Login response includes full user object with profile
