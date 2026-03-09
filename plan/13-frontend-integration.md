# Step 13 — Frontend Integration Contract

> **Phase**: F (Integration)  
> **Dependencies**: All previous steps  
> **Produces**: API contract documentation, frontend route recommendations, middleware strategy

---

## Objective

Define the exact contract between `auth_services` (port 5000) and `poruta-front-end` (port 3000). This document tells the frontend team: what endpoints to call, what to send, what to expect back, how to store tokens, and what routes to build. **No frontend code is written in this step** — only the specification.

---

## API Base URL

```
Development: http://localhost:5000
Production:  https://auth.poruta.com (or configure via NEXT_PUBLIC_AUTH_URL)
```

Frontend env variable: `NEXT_PUBLIC_AUTH_URL=http://localhost:5000`

---

## Token Transport Strategy

### Access Token
- **Where**: Memory (JavaScript variable in auth store)
- **NOT in**: localStorage, sessionStorage, cookies
- **How**: Sent as `Authorization: Bearer <token>` header on every API request
- **Lifetime**: 15 minutes
- **Refresh**: Frontend refreshes automatically before expiry (e.g., at 14 minutes)
- **On page reload**: Lost (by design — frontend calls `/auth/refresh` using the cookie)

### Refresh Token
- **Where**: httpOnly cookie (set by auth service via `Set-Cookie` header)
- **Cookie name**: `poruta_refresh_token`
- **Cookie attributes**: `HttpOnly; Secure; SameSite=Strict; Path=/auth/refresh; Max-Age=604800`
- **Sent automatically**: Browser sends it only to `POST /auth/refresh` (Path restriction)
- **Lifetime**: 7 days
- **Cannot be read by JavaScript**: Protected from XSS

### Token Lifecycle

```
Page Load → Check cookie exists (implicit — browser handles it)
         → POST /auth/refresh (browser sends cookie automatically)
         → Receive new access_token + new cookie
         → Store access_token in memory
         → User is authenticated

API Request → Include Authorization: Bearer <access_token>
           → If 401 → POST /auth/refresh → retry request
           → If refresh also fails → redirect to /login

Logout → POST /auth/logout → cookie cleared by server (Max-Age=0)
       → Clear access_token from memory
       → Redirect to /login
```

---

## Frontend Routes to Build

| Route | Purpose | Protected |
|-------|---------|-----------|
| `/login` | Email + password login form | No |
| `/signup` | Self-registration (importer/agency_manager) | No |
| `/signup/invite` | Invited registration (agent/inspector/government) | No (token-gated) |
| `/verify-email` | Shows "check your email" + handles token validation | No |
| `/forgot-password` | Request password reset email | No |
| `/reset-password` | Set new password with reset token | No |
| `/onboarding/profile` | Profile completion form (after email verify) | Yes (verified but incomplete) |
| All existing routes | Dashboard, declarations, etc. | Yes (complete profile required) |

### Route Group Suggestion

```
poruta-front-end/src/app/
├── (auth)/                      # Public auth pages (no sidebar, no header)
│   ├── login/page.tsx
│   ├── signup/page.tsx
│   ├── signup/invite/page.tsx
│   ├── verify-email/page.tsx
│   ├── forgot-password/page.tsx
│   └── reset-password/page.tsx
├── (onboarding)/                # Post-signup, pre-dashboard
│   └── onboarding/
│       └── profile/page.tsx
├── (authenticated)/             # Existing protected routes
│   ├── layout.tsx               # MainLayout (sidebar + header)
│   └── ...existing routes...
└── (standalone)/                # Existing standalone routes
```

---

## Middleware Strategy (middleware.ts)

```typescript
// Pseudocode — actual implementation in frontend integration phase

export function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname;

  // Public routes — no auth check
  const publicRoutes = ['/login', '/signup', '/verify-email', '/forgot-password', '/reset-password'];
  if (publicRoutes.some(route => pathname.startsWith(route))) {
    return NextResponse.next();
  }

  // Check for refresh token cookie
  const refreshToken = request.cookies.get('poruta_refresh_token');
  if (!refreshToken) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  // Note: We cannot validate the access token in middleware (it's in memory)
  // The refresh token cookie's presence is a proxy for "user has an active session"
  // Actual access token validation happens client-side via the auth store

  return NextResponse.next();
}
```

---

## Auth Store Updates (store/auth.ts)

The current Zustand store will need these changes:

```typescript
// New state
interface AuthState {
  accessToken: string | null;        // In-memory (not persisted)
  user: UserResponse | null;         // From login/refresh response
  isLoading: boolean;                // True during initial auth check
  isAuthenticated: boolean;          // Computed: accessToken !== null

  // Actions
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, role: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshTokens: () => Promise<void>;  // Called on page load + before expiry
  completeProfile: (data: ProfileData) => Promise<void>;
  updateProfile: (data: Partial<ProfileData>) => Promise<void>;
}
```

**Key difference from current**: No more `FAKE_USERS`, no more `setRole()`. The user's role comes from the server. Role switching (for demo purposes) would need a separate mechanism.

---

## CORS Configuration

Auth service must allow:
```
Origin: http://localhost:3000 (dev) / https://poruta.com (prod)
Methods: GET, POST, PATCH, DELETE, OPTIONS
Headers: Authorization, Content-Type
Credentials: true (required for cookies)
```

`credentials: true` is necessary for the browser to send and accept cookies cross-origin. The frontend must also set `credentials: 'include'` on fetch requests.

---

## Error Response Format

All auth service errors follow this structure:

```json
{
  "error": "error_type",
  "message": "Human-readable message",
  "details": null | ["list", "of", "specific", "issues"]
}
```

Frontend should display `message` to the user. `details` provides specific field-level errors (e.g., password violations).

---

## API Flow Diagrams

### Self-Signup (Importer)
```
1. POST /auth/signup → 201 "Check your email"
2. User clicks email link → GET /verify-email?token=X
3. Frontend calls POST /auth/verify-email → 200 "Verified"
4. Redirect to /login
5. POST /auth/login → 200 {tokens, user{profile_completed: false}}
6. Frontend detects profile_completed=false → redirect to /onboarding/profile
7. POST /auth/profile/complete → 200 {user{profile_completed: true}}
8. Redirect to /dashboard (importer)
```

### Invited Signup (Agent)
```
1. Agent Manager calls POST /auth/invite → 201 "Invitation sent"
2. Agent receives email → clicks link → /signup/invite?token=X
3. Frontend calls GET /auth/invite/validate?token=X → 200 {email, role, agency}
4. Frontend pre-fills form with email, shows role + agency info
5. Agent fills password, name, phone → POST /auth/signup/invited → 201 {tokens, user}
6. Redirect to /dashboard (agent) — fully onboarded in one step
```

### Login
```
1. POST /auth/login → 200 {tokens, user}
2. Store access_token in memory
3. Refresh token set via Set-Cookie (automatic)
4. If user.profile_completed=false → redirect to /onboarding/profile
5. Else → redirect to role-specific dashboard
```

### Page Reload (Session Restoration)
```
1. Page loads → auth store initializes → isLoading=true
2. Call POST /auth/refresh (browser sends poruta_refresh_token cookie)
3. If 200 → store new access_token, set user, isAuthenticated=true
4. If 401 → clear state, isAuthenticated=false, redirect to /login
5. isLoading=false
```

### Token Refresh (Automatic)
```
1. Set timer for access token refresh (e.g., at 14 minutes)
2. Timer fires → POST /auth/refresh
3. If 200 → update access_token in memory, reset timer
4. If 401 → redirect to /login
```

---

## Admin User Management Endpoints

For the admin dashboard's user management page:

```
GET /auth/users?page=1&role=agent&search=Marie
→ Returns paginated user list with profile info

PATCH /auth/users/{id}/deactivate
→ Soft-deactivates user, revokes all their sessions

PATCH /auth/users/{id}/activate
→ Reactivates user
```

Admin cannot deactivate other admin users — the API enforces this.

---

## Acceptance Criteria

- [ ] API contract documented for every endpoint
- [ ] Token transport strategy clearly defined
- [ ] Frontend route list finalized
- [ ] middleware.ts strategy described
- [ ] Auth store interface defined
- [ ] CORS requirements specified
- [ ] Error response format consistent across all endpoints
- [ ] Flow diagrams cover: self-signup, invited signup, login, page reload, token refresh
- [ ] Admin user management endpoints documented
