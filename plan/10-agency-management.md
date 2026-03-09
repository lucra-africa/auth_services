# Step 10 — Agency Management

> **Phase**: D (Admin & Agency)  
> **Dependencies**: Step 09 (admin exists)  
> **Produces**: Agency CRUD endpoints

---

## Objective

System Admin creates and manages agencies in the auth system. Agencies are the organizational entities that Agency Managers associate with and that Custom Agents are linked to through invitations. Agencies must exist before Agency Managers can complete their profiles or invite Agents.

---

## Why Agencies Live in auth_services

Agencies are part of the identity and access control model:
- Agency Managers prove their affiliation during profile completion (choosing an agency)
- Agent invitations reference an agency (agents are auto-linked)
- The `user_agency` join table defines organizational relationships

Business data about agencies (contracts, revenue, performance metrics) belongs in the main backend. auth_services only tracks: name, registration number, and user associations.

---

## Endpoints

### POST /auth/agencies

**Auth**: Admin only.

#### Request
```json
{
  "name": "Swift Customs Agency",
  "registration_number": "RCA-2024-00153",
  "address": "KG 123 St, Kigali, Rwanda",
  "phone": "+250788100200",
  "email": "info@swiftcustoms.rw"
}
```

#### Validation

```
1. name: required, non-empty, max 255 chars
2. registration_number: required, unique (check DB)
3. address, phone, email: optional
```

#### Business Logic

```
1. Check registration_number uniqueness → 409 if duplicate
2. Create Agency record:
   - created_by = current_user.id (admin)
   - is_active = true
3. Log AGENCY_CREATED action:
   - metadata: {"agency_name": name, "registration_number": reg_num}
4. Return agency
```

#### Response (201)
```json
{
  "id": "uuid",
  "name": "Swift Customs Agency",
  "registration_number": "RCA-2024-00153",
  "address": "KG 123 St, Kigali, Rwanda",
  "phone": "+250788100200",
  "email": "info@swiftcustoms.rw",
  "is_active": true,
  "created_at": "2026-03-08T10:00:00Z"
}
```

---

### GET /auth/agencies

**Auth**: Admin or Agency Manager.

Returns list of active agencies. Agency Managers see this list during profile completion (to select their agency). Admins see all agencies including inactive ones.

#### Query Parameters
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `limit` | int | 20 | Items per page (max 100) |
| `search` | string | — | Search by name or registration number |
| `include_inactive` | bool | false | Admin only — include deactivated agencies |

#### Response (200)
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Swift Customs Agency",
      "registration_number": "RCA-2024-00153",
      "is_active": true,
      "agent_count": 5,
      "manager_count": 1
    }
  ],
  "total": 12,
  "page": 1,
  "limit": 20
}
```

The `agent_count` and `manager_count` are computed from the `user_agency` table — useful for admins to see agency sizes.

**Non-admin users**: `include_inactive` is silently ignored (they always see only active agencies).

---

### GET /auth/agencies/{id}

**Auth**: Admin or Agency Manager (if manager is linked to this agency).

#### Response (200)
```json
{
  "id": "uuid",
  "name": "Swift Customs Agency",
  "registration_number": "RCA-2024-00153",
  "address": "KG 123 St, Kigali, Rwanda",
  "phone": "+250788100200",
  "email": "info@swiftcustoms.rw",
  "is_active": true,
  "created_at": "2026-03-08T10:00:00Z",
  "created_by": {
    "id": "admin-uuid",
    "email": "admin@poruta.io",
    "name": "System Administrator"
  },
  "members": [
    {
      "id": "user-uuid",
      "email": "p.ndayisaba@swiftcustoms.rw",
      "name": "Patrick Ndayisaba",
      "role_in_agency": "manager",
      "joined_at": "2026-03-08T10:30:00Z"
    },
    {
      "id": "user-uuid",
      "email": "mc.uwimana@swiftcustoms.rw",
      "name": "Marie-Claire Uwimana",
      "role_in_agency": "agent",
      "joined_at": "2026-03-08T11:00:00Z"
    }
  ]
}
```

---

### PATCH /auth/agencies/{id}

**Auth**: Admin only.

#### Request (partial update)
```json
{
  "name": "Swift Customs Agency Ltd",
  "phone": "+250788100300"
}
```

**Updatable fields**: name, address, phone, email  
**Non-updatable**: registration_number (immutable — official government identifier)

#### Business Logic

```
1. Load agency by ID → 404 if not found
2. Update provided fields
3. Set updated_at = now
4. Log action with metadata: {"changed_fields": ["name", "phone"]}
5. Return updated agency
```

---

### DELETE /auth/agencies/{id}

**Auth**: Admin only.

Soft-deactivate: sets `is_active = false`. Does NOT delete the record or remove user associations.

#### Business Logic

```
1. Load agency by ID → 404 if not found
2. If already inactive → 400 "Agency is already deactivated"
3. Set is_active = false
4. Note: existing user_agency records remain (members keep their historical association)
5. New profile completions cannot select this agency
6. New invitations cannot reference this agency
7. Log action
8. Return 200
```

#### Response (200)
```json
{
  "message": "Agency deactivated successfully",
  "id": "uuid",
  "name": "Swift Customs Agency"
}
```

### Reactivation

No separate endpoint — admins use `PATCH /auth/agencies/{id}` with `{"is_active": true}` (adding `is_active` to updatable fields for admin).

---

## Impact on Other Flows

1. **Agency Manager profile completion** (Step 08): The `agency_id` in the profile completion form is validated against active agencies. Deactivated agencies are not selectable.

2. **Agent invitations** (Step 07): When an agency manager invites an agent, the manager's agency is auto-resolved. If the manager's agency has been deactivated, the invitation fails with "Your agency has been deactivated. Contact your administrator."

3. **Existing agents/managers**: If an agency is deactivated, existing users linked to it can still log in and work. The deactivation only prevents new associations. If the admin wants to prevent access entirely, they should deactivate individual user accounts.

---

## Acceptance Criteria

- [ ] Admin can create an agency with valid data (201)
- [ ] Duplicate registration_number returns 409
- [ ] Non-admin cannot create agencies (403)
- [ ] GET /auth/agencies returns paginated list
- [ ] GET /auth/agencies supports search by name
- [ ] Admin sees inactive agencies when requested
- [ ] Agency Manager sees only active agencies
- [ ] GET /auth/agencies/{id} returns agency with members
- [ ] Agency Manager can only view their own agency's detail
- [ ] PATCH updates specified fields only
- [ ] registration_number cannot be updated
- [ ] DELETE soft-deactivates (is_active=false)
- [ ] AGENCY_CREATED logged for new agencies
- [ ] Deactivated agencies cannot be selected during profile completion
