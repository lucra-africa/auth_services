# Step 08 — Profile Completion

> **Phase**: C (Invitation & Profile)  
> **Dependencies**: Phase B (core auth)  
> **Parallel with**: Step 07 (invitation system)  
> **Produces**: Profile complete, get, and update endpoints

---

## Objective

After self-signup users (importers and agency managers) verify their email, they must complete their profile before accessing the platform. This step collects role-dependent information: name, phone, company (importers), and agency association (agency managers).

**Note**: Invited users (agents, inspectors, government) skip this — their profile is completed during the invitation signup flow (Step 07).

---

## Onboarding State Machine

```
Self-signup user flow:
  SIGNUP → [is_email_verified=false, profile_completed=false]
  ↓ (verify email)
  VERIFIED → [is_email_verified=true, profile_completed=false]
  ↓ (complete profile)
  COMPLETE → [is_email_verified=true, profile_completed=true]
  ↓ (can now access the full platform)

Invited user flow:
  INVITED SIGNUP → [is_email_verified=true, profile_completed=true]
  ↓ (can immediately access the platform — no intermediate steps)
```

The frontend uses these two flags to determine where to redirect the user:
- Not verified → redirect to "check your email" page
- Verified but profile incomplete → redirect to `/onboarding/profile`
- Verified and complete → redirect to role-specific dashboard

---

## Endpoints

### POST /auth/profile/complete

**Auth**: Required. User must have `is_email_verified=true` and `profile_completed=false`.

This endpoint is used ONCE during onboarding. After profile is completed, further updates use `PATCH /auth/profile`.

#### Request

**For Importers:**
```json
{
  "first_name": "Jean-Pierre",
  "last_name": "Habimana",
  "phone": "+250788123456",
  "company_name": "Kigali Electronics Ltd"
}
```

**For Agency Managers:**
```json
{
  "first_name": "Patrick",
  "last_name": "Ndayisaba",
  "phone": "+250788234567",
  "agency_id": "uuid-of-existing-agency"
}
```

#### Validation

```
1. User must be authenticated (access token)
2. User must have is_email_verified=true
3. User must have profile_completed=false (prevents re-completing)
4. Required fields: first_name, last_name, phone
5. Role-specific validation:
   - IMPORTER: company_name is required (non-empty string)
   - AGENCY_MANAGER: agency_id is required, must reference an existing active agency
```

#### Business Logic

```
1. Validate required fields per role
2. Create UserProfile record:
   - user_id = current_user.id
   - first_name, last_name, phone
   - company_name (importers only, null for others)
   - avatar_url = null (can be set later)
   - metadata = {}
3. For agency_manager:
   - Validate agency exists and is_active=true
   - Create UserAgency record:
     - user_id, agency_id
     - role_in_agency = AgencyRole.MANAGER
     - joined_at = now
4. Set user.profile_completed = true
5. Log PROFILE_UPDATED action
6. Return updated user with profile
```

#### Response (200)
```json
{
  "message": "Profile completed successfully",
  "user": {
    "id": "uuid",
    "email": "jp@kigalielec.rw",
    "role": "importer",
    "is_email_verified": true,
    "profile_completed": true,
    "profile": {
      "first_name": "Jean-Pierre",
      "last_name": "Habimana",
      "phone": "+250788123456",
      "company_name": "Kigali Electronics Ltd",
      "avatar_url": null,
      "metadata": {}
    }
  }
}
```

#### Errors
| Code | Condition |
|------|-----------|
| 400 | Profile already completed |
| 403 | Email not verified |
| 422 | Missing required fields (company_name for importer, agency_id for manager) |
| 404 | Agency not found (for agency_manager) |
| 400 | Agency is deactivated |

---

### GET /auth/profile

**Auth**: Required (any authenticated user).

Returns the current user's profile information.

#### Response (200)
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "role": "importer",
  "is_email_verified": true,
  "profile_completed": true,
  "profile": {
    "first_name": "Jean-Pierre",
    "last_name": "Habimana",
    "phone": "+250788123456",
    "company_name": "Kigali Electronics Ltd",
    "avatar_url": null,
    "metadata": {}
  },
  "agency": null,
  "created_at": "2026-03-08T10:00:00Z",
  "last_login_at": "2026-03-08T14:30:00Z"
}
```

For users linked to an agency, the `agency` field is populated:
```json
{
  "agency": {
    "id": "uuid",
    "name": "Swift Customs Agency",
    "role_in_agency": "agent"
  }
}
```

---

### PATCH /auth/profile

**Auth**: Required (any authenticated user with completed profile).

#### Request (partial — only include fields to update)
```json
{
  "phone": "+250788999999",
  "company_name": "New Company Name"
}
```

**Updatable fields**: first_name, last_name, phone, company_name, metadata

**Non-updatable fields**: email (separate flow), role (admin only), agency (admin only)

#### Business Logic

```
1. Get current user's profile
2. Update only provided fields (partial update)
3. Log PROFILE_UPDATED action with changed fields in metadata
4. Return updated user
```

#### Response (200)
Same structure as GET /auth/profile.

---

## Agency Manager — Agency Selection

When an agency manager completes their profile, they must select an existing agency. This means agencies must be created by an admin BEFORE agency managers can complete onboarding.

### Frontend UX Implication

The profile completion form for agency managers should include a dropdown/search of available agencies (fetched from `GET /auth/agencies`). If no agencies exist yet, the form should show a message: "No agencies available. Contact your system administrator."

### Why not allow managers to create agencies?

Agency creation requires registration numbers, official addresses, and other data that should be verified by an admin. Letting managers self-create agencies would bypass this verification step. The admin creates the agency entity; the manager associates themselves with it.

---

## Acceptance Criteria

- [ ] Importer can complete profile with first_name, last_name, phone, company_name
- [ ] Agency Manager can complete profile with first_name, last_name, phone, agency_id
- [ ] Importer without company_name gets 422
- [ ] Agency Manager without agency_id gets 422
- [ ] Agency Manager with invalid agency_id gets 404
- [ ] Already-completed profile returns 400 on POST /auth/profile/complete
- [ ] Unverified user gets 403 on POST /auth/profile/complete
- [ ] GET /auth/profile returns user with profile and agency info
- [ ] PATCH /auth/profile updates specified fields only
- [ ] PROFILE_UPDATED action logged with changed fields
- [ ] User's profile_completed flag is set to true after completion
