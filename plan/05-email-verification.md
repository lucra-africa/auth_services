# Step 05 — Email Verification

> **Phase**: B (Core Auth)  
> **Dependencies**: Step 04 (signup creates verification tokens)  
> **Produces**: `POST /auth/verify-email` endpoint, resend verification endpoint

---

## Objective

Allow users to verify their email address by clicking the link in the verification email. The token is validated, the user is marked as verified, and they're directed to complete their profile.

---

## Endpoints

### POST /auth/verify-email

#### Request
```json
{
  "token": "urlsafe-base64-token-string"
}
```

#### Validation Steps

1. Hash the incoming token with SHA-256
2. Look up the hash in `email_verification_tokens`
3. Check token exists — if not, return 400 "Invalid or expired verification token"
4. Check `used_at` is NULL — if already used, return 400 "Token has already been used"
5. Check `expires_at > now` — if expired, return 400 "Verification token has expired. Please request a new one"
6. Load the associated user

#### Business Logic

```
1. Mark token as used: set used_at = now
2. Mark user as verified: set is_email_verified = True
3. Log EMAIL_VERIFY action to auth_logs
4. Return success with appropriate redirect info
```

#### Response (200)
```json
{
  "message": "Email verified successfully",
  "redirect": "/onboarding/profile"
}
```

#### Error Responses
| Code | Condition | Body |
|------|-----------|------|
| 400 | Invalid token | `{"error": "invalid_token", "message": "Invalid or expired verification token"}` |
| 400 | Already used | `{"error": "token_used", "message": "This verification link has already been used"}` |
| 400 | Expired | `{"error": "token_expired", "message": "Verification token has expired. Please request a new one."}` |

---

### POST /auth/verify-email/resend

Allows users who didn't receive or whose token expired to request a new verification email.

#### Request
```json
{
  "email": "user@example.com"
}
```

#### Business Logic

```
1. Look up user by email
2. If user not found → return 200 (prevent email enumeration)
3. If user already verified → return 200 (same response, no action)
4. Invalidate any existing unused verification tokens for this user
5. Generate new token, hash, store in email_verification_tokens (24h expiry)
6. Send verification email
7. Return 200
```

#### Response (200 — always, regardless of email existence)
```json
{
  "message": "If an account exists with this email, a verification link has been sent."
}
```

This constant response prevents attackers from discovering which emails have accounts.

---

## Security Notes

1. **Token single-use**: Once verified, the token is marked `used_at = now`. Replaying it fails.
2. **No email enumeration**: Both the verify and resend endpoints give the same response regardless of whether the email exists.
3. **Token invalidation on resend**: When a user requests a new token, old tokens for that user are left to expire naturally (they're not deleted, but a new one is created). If the old token is used before expiry, it still works — this is acceptable because both tokens prove the same thing (email ownership).
4. **Already-verified users**: If a user is already verified and someone tries to verify again (e.g., clicking the link twice), return success — idempotent behavior.

---

## Acceptance Criteria

- [ ] `POST /auth/verify-email` with valid token marks user as verified
- [ ] `POST /auth/verify-email` with invalid token returns 400
- [ ] `POST /auth/verify-email` with expired token returns 400 with "request a new one" message
- [ ] `POST /auth/verify-email` with used token returns 400
- [ ] `POST /auth/verify-email/resend` sends new verification email
- [ ] `POST /auth/verify-email/resend` with non-existent email returns 200 (no enumeration)
- [ ] `POST /auth/verify-email/resend` with already-verified user returns 200 (no action)
- [ ] EMAIL_VERIFY action logged in auth_logs
