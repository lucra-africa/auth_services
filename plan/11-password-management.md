# Step 11 — Password Management

> **Phase**: E (Security & Logging)  
> **Dependencies**: Phase B (core auth)  
> **Parallel with**: Phase D  
> **Produces**: Forgot password, reset password, change password endpoints

---

## Objective

Three password-related flows: forgot (request reset email), reset (use token to set new password), and change (authenticated user updates their own password). All flows enforce password strength, log actions, and revoke active sessions where appropriate.

---

## Endpoints

### POST /auth/password/forgot

**Auth**: None required.

#### Request
```json
{
  "email": "user@example.com"
}
```

#### Business Logic

```
1. Look up user by email
2. ALWAYS return 200 (prevent email enumeration)
3. If user found AND is_active=true AND is_email_verified=true:
   a. Invalidate existing unused reset tokens for this user (set used_at = now)
   b. Generate new token: secrets.token_urlsafe(32)
   c. Hash with SHA-256, store in password_reset_tokens:
      - user_id, token_hash, expires_at = now + 1 hour
   d. Send password reset email:
      - URL: {frontend_url}/reset-password?token={raw_token}
   e. Log PASSWORD_RESET_REQUESTED action (not PASSWORD_RESET — that's for successful resets)
4. If user not found, inactive, or unverified:
   - Do nothing (but return same 200 response)
   - Log action with metadata: {"reason": "user_not_found"} (for admin monitoring)
```

#### Response (200 — always)
```json
{
  "message": "If an account exists with this email, a password reset link has been sent."
}
```

**Security**: The constant response prevents attackers from discovering which emails have accounts (email enumeration attack).

**Reset token expiry**: 1 hour (shorter than email verification's 24 hours — password resets are more security-sensitive).

---

### POST /auth/password/reset

**Auth**: None required (token-authenticated).

#### Request
```json
{
  "token": "urlsafe-token-string",
  "new_password": "N3w!Str0ng#Pass"
}
```

#### Business Logic

```
1. Hash token, look up in password_reset_tokens
2. Validate:
   - Token exists → 400 "Invalid or expired reset token"
   - Token not used (used_at is null) → 400 "Token has already been used"
   - Token not expired (expires_at > now) → 400 "Reset token has expired"
3. Validate new password strength
4. Load user by token's user_id
5. Check user is_active → 400 "Account is deactivated"
6. Hash new password with Argon2id
7. Update user:
   - password_hash = new hash
   - failed_login_count = 0
   - locked_until = null (unlock if was locked)
8. Mark reset token as used: used_at = now
9. Revoke ALL refresh tokens for this user:
   - UPDATE refresh_tokens SET revoked_at = now WHERE user_id = X AND revoked_at IS NULL
   - This forces re-login on all devices (security: if password was compromised, attacker's sessions are killed)
10. Log PASSWORD_RESET action
11. Return success
```

#### Response (200)
```json
{
  "message": "Password reset successfully. Please log in with your new password."
}
```

#### Errors
| Code | Condition |
|------|-----------|
| 400 | Invalid/expired/used token |
| 422 | New password doesn't meet requirements |

---

### POST /auth/password/change

**Auth**: Required (access token).

For authenticated users who want to change their password while logged in.

#### Request
```json
{
  "current_password": "0ld!P@ssw0rd",
  "new_password": "N3w!Str0ng#Pass"
}
```

#### Business Logic

```
1. Get current user (from access token)
2. Verify current_password against stored hash (Argon2id)
   - Wrong → 401 "Current password is incorrect"
3. Validate new password strength
4. Check new password != current password → 400 "New password must be different from current password"
5. Hash new password with Argon2id
6. Update user.password_hash
7. Revoke all OTHER refresh tokens (not the current session):
   - Revoke all refresh tokens for this user EXCEPT identify the current session
   - Actually: revoke ALL refresh tokens. The current access token remains valid for its 15-min lifetime.
     After that, the user gets a new refresh token on their next login.
     This is simpler and equally secure — one forced re-login is acceptable after password change.
8. Log PASSWORD_CHANGED action
9. Return success with new token pair (auto re-login)
```

#### Response (200)
```json
{
  "message": "Password changed successfully",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 900
}
```

Returning new tokens avoids the user being immediately logged out on their current device after changing their password.

#### Errors
| Code | Condition |
|------|-----------|
| 401 | Current password is incorrect |
| 400 | New password is same as current password |
| 422 | New password doesn't meet requirements |

---

## Email Template (password_reset.html)

```
Subject: Reset your Poruta password

Body:
- "Hi,"
- "We received a request to reset your password."
- CTA button: "Reset Password"
- Link: {frontend_url}/reset-password?token={token}
- "This link expires in 1 hour."
- "If you didn't request a password reset, your account is still secure. You can safely ignore this email."
- "If you're concerned about unauthorized access, please change your password immediately."
```

---

## Security Notes

1. **No email enumeration**: `/forgot` always returns 200 with the same message
2. **Short expiry**: Reset tokens expire in 1 hour (vs. 24 hours for email verification)
3. **Single-use**: Token is marked used immediately
4. **Session revocation**: Password reset and change both revoke all refresh tokens, forcing re-login on all devices
5. **Unlock on reset**: If the account was locked due to failed attempts, a successful password reset unlocks it (the user proved ownership via their email)
6. **Current password required for change**: An attacker with a stolen access token cannot change the password without knowing the current one

---

## Acceptance Criteria

- [ ] POST /auth/password/forgot returns 200 for both existing and non-existing emails
- [ ] Reset email is sent to existing, active, verified users
- [ ] Reset email is NOT sent to non-existing, inactive, or unverified users
- [ ] POST /auth/password/reset with valid token changes the password
- [ ] Invalid/expired/used reset token returns 400
- [ ] Weak new password returns 422
- [ ] Password reset revokes all refresh tokens
- [ ] Password reset unlocks locked accounts
- [ ] POST /auth/password/change requires valid current password
- [ ] Password change revokes other sessions and returns new tokens
- [ ] Same password as current returns 400
- [ ] PASSWORD_RESET and PASSWORD_CHANGED actions logged
