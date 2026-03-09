# Step 07 — Invitation System

> **Phase**: C (Invitation & Profile)  
> **Dependencies**: Phase B (core auth working)  
> **Produces**: Invitation sending, validation, and invited-user signup endpoints

---

## Objective

Implement the invitation-based registration flow for restricted roles: Agency Manager invites Agents, Government invites Inspectors, Admin invites Government users. The invitation generates a single-use, 24-hour token sent via email. Recipients click the link, set their password, complete their profile, and are automatically verified and linked to the appropriate organization.

---

## Role-Based Invitation Permissions

| Inviter Role | Can Invite | Required Fields |
|--------------|-----------|-----------------|
| Agency Manager | `agent` | email, agency_id (auto-set to manager's agency) |
| Government | `inspector` | email |
| Admin | `government` | email |
| Admin | `admin` (only via CLI — NOT via this endpoint) | — |

All other combinations are rejected with 403.

---

## Endpoints

### POST /auth/invite

**Auth**: Required. Inviter must have appropriate role.

#### Request
```json
{
  "email": "newagent@example.com",
  "role": "agent"
}
```

For agency_manager inviting an agent, `agency_id` is automatically resolved from the manager's `user_agency` record. The API does not accept `agency_id` in the request body — it is derived server-side to prevent manipulation.

#### Validation

```
1. Check inviter's role is allowed to invite the target role (permission matrix above)
2. Check email is not already registered (return 409 if exists)
3. Check no pending (unused, unexpired) invitation exists for this email (return 409 if exists)
4. For agent invitations: resolve agency_id from inviter's user_agency record
   - If inviter is not linked to any agency → 400 "You must be associated with an agency to invite agents"
```

#### Business Logic

```
1. Generate token: secrets.token_urlsafe(32)
2. Hash token with SHA-256
3. Create InvitationToken record:
   - token_hash, email, role
   - invited_by = current_user.id
   - agency_id = resolved agency (or null for non-agent roles)
   - expires_at = now + 24 hours
4. Send invitation email:
   - URL: {frontend_url}/signup/invite?token={raw_token}
   - Template includes: inviter's name, role being invited to, agency name (if applicable)
5. Log INVITATION_SENT action:
   - metadata: {"invited_email": email, "role": role, "agency_id": agency_id}
6. Return success
```

#### Response (201)
```json
{
  "message": "Invitation sent to newagent@example.com",
  "expires_at": "2026-03-09T14:30:00Z"
}
```

#### Errors
| Code | Condition |
|------|-----------|
| 403 | Inviter role cannot invite target role |
| 409 | Email already registered |
| 409 | Pending invitation already exists for this email |
| 400 | Agency manager not linked to an agency |

---

### GET /auth/invite/validate?token=xxx

**Auth**: None required (pre-signup endpoint).

Used by the frontend to pre-fill the signup form when a user clicks the invitation link.

#### Business Logic

```
1. Hash token, look up in invitation_tokens
2. Validate: exists, not used, not expired
3. Return invitation details (but NOT the token hash)
```

#### Response (200)
```json
{
  "email": "newagent@example.com",
  "role": "agent",
  "agency": {
    "id": "uuid",
    "name": "Swift Customs Agency"
  },
  "invited_by": "Patrick Ndayisaba",
  "expires_at": "2026-03-09T14:30:00Z"
}
```

The frontend uses this to display: "You've been invited to join Swift Customs Agency as a Customs Agent by Patrick Ndayisaba."

#### Errors
| Code | Condition |
|------|-----------|
| 400 | Invalid, used, or expired token |

---

### POST /auth/signup/invited

**Auth**: None (token-authenticated).

#### Request
```json
{
  "token": "urlsafe-token-string",
  "password": "Str0ng!P@ssw0rd",
  "first_name": "Marie-Claire",
  "last_name": "Uwimana",
  "phone": "+250788654321"
}
```

#### Business Logic

```
1. Hash token, look up invitation
2. Validate: exists, not used, not expired
3. Validate password strength (same rules as self-signup)
4. Check email not already registered (edge case: someone registered between invitation sent and used)

5. Create User record:
   - email = invitation.email
   - password_hash = Argon2id(password)
   - role = invitation.role
   - is_email_verified = TRUE (trust chain: invitation email proves ownership)
   - is_active = TRUE
   - profile_completed = TRUE

6. Create UserProfile:
   - first_name, last_name, phone
   - company_name = null (agents don't have their own company)
   - metadata = {} 

7. If role is agent and invitation has agency_id:
   - Create UserAgency record:
     - user_id, agency_id
     - role_in_agency = AgencyRole.AGENT
     - joined_at = now

8. Mark invitation token as used: used_at = now

9. Log INVITATION_USED + SIGNUP actions:
   - metadata: {"invited_by": invitation.invited_by, "role": invitation.role, "agency_id": invitation.agency_id}

10. Create access + refresh tokens (auto-login after signup)
11. Return token response with user object (same format as login response)
```

#### Response (201)
Same structure as login response — the user is immediately logged in.

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "email": "newagent@example.com",
    "role": "agent",
    "is_email_verified": true,
    "profile_completed": true,
    "profile": {
      "first_name": "Marie-Claire",
      "last_name": "Uwimana",
      "phone": "+250788654321"
    }
  }
}
```

---

## Email Template (invitation.html)

```
Subject: You've been invited to Poruta

Body:
- "Hi,"
- "{inviter_name} has invited you to join Poruta as a {role_label}."
- If agent: "You'll be joining {agency_name}."
- CTA button: "Accept Invitation"
- Link: {frontend_url}/signup/invite?token={token}
- "This invitation expires in 24 hours."
- "If you weren't expecting this invitation, you can safely ignore this email."
```

---

## Security Notes

1. **Token never stored in plaintext**: Only SHA-256 hash in DB. Raw token exists only in the email URL and in-flight during validation.
2. **Single-use**: `used_at` is set immediately when the invitation is consumed. Replaying the token fails.
3. **24-hour expiry**: Short window limits the exposure if the email is intercepted.
4. **Server-side agency resolution**: Agency managers cannot specify an arbitrary `agency_id` — it's derived from their own `user_agency` record. Prevents agents from being linked to agencies they shouldn't belong to.
5. **Email pre-verified**: Invited users skip email verification because the invitation email itself proves email ownership (only someone with access to the inbox can know the token).
6. **No race condition**: The invitation is marked as used in the same transaction that creates the user. If two requests arrive simultaneously with the same token, only one succeeds (database uniqueness + used_at check).

---

## Acceptance Criteria

- [ ] Agency Manager can invite an agent (returns 201, email sent)
- [ ] Government user can invite an inspector
- [ ] Admin can invite a government user
- [ ] Importer cannot invite anyone (403)
- [ ] Agent cannot invite anyone (403)
- [ ] Cannot invite an email that's already registered (409)
- [ ] Cannot create duplicate pending invitation (409)
- [ ] Validate endpoint returns invitation details without requiring auth
- [ ] Invalid/expired/used token on validate returns 400
- [ ] Invited signup creates user with email pre-verified, profile complete
- [ ] Agent invited signup auto-links to correct agency
- [ ] Invited signup returns tokens (auto-login)
- [ ] Invitation token marked as used after successful signup
- [ ] INVITATION_SENT and INVITATION_USED logged in auth_logs
