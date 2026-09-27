# ADR-007: Single-User Authentication and Private API

Status: Accepted

Date: 2026-09-27

## Context

Milestone 2 exposes private data (the canonical profile, opportunities, eligibility results, application notes) through an HTTP API and a browser UI. [ADR-004](ADR-004-technology-stack.md) requires $0/month with no payment method, so no paid or hosted identity provider. The application is:

```text
single-user
private at runtime
public source code
```

There is exactly one owner. There is no public signup and no multi-user product design. The source code is public ([ENGINEERING_GUIDELINES.md §16](../../ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)), so nothing about the owner's credentials may live in Git.

## Decision

### 1. Username/password with Argon2id

- One `auth_users` table: `id`, `username` (unique), `password_hash`, `is_active`, timestamps. No email, real name, or phone.
- Passwords are hashed with **Argon2id** through [`pwdlib[argon2]`](https://github.com/frankie567/pwdlib) using `PasswordHash.recommended()` (argon2-cffi defaults: `m=65536 KiB, t=3, p=4`). We never implement hashing ourselves.
- Minimum password length 12 (CLI-enforced). No maximum below what Argon2 handles; the login schema caps input at 1024 characters to bound hashing work.
- Login with an unknown username still runs a hash verification against a fixed dummy hash, so response time doesn't reveal whether the username exists. The failure message is always the same generic text.
- Not used: JWTs in `localStorage`, plaintext passwords, HTTP Basic as the product login, hard-coded or committed credentials, public registration, password-reset email.

Dependency review (required by [ADR-005](ADR-005-source-and-profile-ingestion-strategy.md) and §16):

| Package | Version | License | Role |
|---|---|---|---|
| `pwdlib` | 0.3.x | MIT | Password hashing API (by the FastAPI Users author) |
| `argon2-cffi` | 25.x | MIT | Argon2 implementation (installed by the `argon2` extra) |
| `argon2-cffi-bindings` | 26.x | MIT | C bindings to the reference Argon2 |
| `cffi` / `pycparser` | 2.x / 3.x | MIT-0 / BSD-3-Clause | Transitive build/runtime deps |

All are permissive, free, and have no network or billing component. No code was copied.

### 2. Owner bootstrap is a CLI, not an endpoint

```bash
python -m app.cli create-owner --username <name>   # prompts twice with getpass
python -m app.cli set-password --username <name>   # password rotation
```

- Interactive entry uses `getpass` (never echoed, never printed, never a command-line argument).
- `--password-stdin` reads one line from standard input, for CI/E2E automation with **synthetic** credentials only.
- `create-owner` refuses if any owner account already exists (single-user; no accidental duplicates).
- `set-password` also revokes all existing sessions of that user.
- There is no registration or password-reset endpoint.

### 3. Opaque server-side sessions

- On login the server generates a session token with `secrets.token_urlsafe(32)` (256 bits of entropy).
- The browser receives it only in a cookie. The database stores only `sha256(token)` in `auth_sessions.token_hash` (unique). A database leak doesn't yield usable cookies. SHA-256 (not a slow hash) is correct here because the token is high-entropy random data, not a human password.
- `auth_sessions`: `id`, `user_id` (FK, cascade), `token_hash`, `created_at`, `expires_at`. Absolute expiry, `SESSION_TTL_HOURS` (default 24). No sliding renewal, so requests don't write to the database.
- Logout **deletes** the row. Login deletes the user's expired sessions and any session presented by the same browser. `set-password` deletes all of them.
- Disabled users (`is_active = false`) can't log in, and their existing sessions stop working.

### 4. Cookie

| Attribute | Value |
|---|---|
| Name | `if_session` |
| `HttpOnly` | always |
| `SameSite` | `Lax` (same-site architecture, see §6) |
| `Secure` | `SESSION_COOKIE_SECURE`, default **true**. Chrome and Firefox accept Secure cookies on `http://localhost`; set `false` only for plain-HTTP development on another host name. Hosted environments must keep it `true`. |
| `Path` | `/` |
| `Max-Age` | the session TTL |

Opaque sessions need no signing key, so there is no cookie secret to manage or leak.

### 5. CSRF: HMAC-derived synchronizer token

Cookies are sent automatically, so every state-changing request needs proof that it came from our own frontend.

- `csrf_token = HMAC-SHA256(key=session_token, msg="csrf")`, base64url. It's returned by `POST /api/auth/login` and `GET /api/auth/session`, and the frontend keeps it **in memory only**.
- `POST`, `PUT`, `PATCH`, and `DELETE` on private endpoints (including logout) must send `X-CSRF-Token`. The server recomputes the value from the session cookie and compares in constant time. Missing or wrong → `403`.
- `GET`, `HEAD`, `OPTIONS`, and `POST /api/auth/login` don't require it.
- This is the "HMAC-based token" variant of the OWASP synchronizer pattern: it's bound to the session, needs no extra column (the verification representation is the session token itself, which the server receives with each request), and survives page reloads because `GET /api/auth/session` can return it again. A cross-site attacker can't read it (same-origin policy) or compute it (they don't know the HttpOnly session token), and a database leak doesn't reveal it (only the SHA-256 of the session token is stored).
- `SameSite=Lax` is a second layer; it isn't relied on alone.

### 6. Same-origin API

- The browser calls relative `/api/...` URLs. In development, the Vite dev server proxies `/api` to `http://localhost:8000`, so the browser only ever talks to one origin.
- The backend no longer installs CORS middleware (and `FRONTEND_ORIGIN` is removed). With no `Access-Control-Allow-Origin` header, browsers refuse cross-origin reads of the API. Same-origin requests don't need CORS.
- **Deployment constraint:** a future hosted deployment must preserve an equivalent same-origin (reverse proxy/rewrite of `/api`) or at least same-site arrangement. A frontend on one provider's random subdomain calling a backend on another provider's random subdomain is **not** an accepted final cookie architecture (`SameSite=Lax` cookies would not be sent, and `SameSite=None` would weaken CSRF defenses). That design needs its own review before production authentication is considered complete.

### 7. One authorization boundary

- Private routers are mounted under a single parent router that has the `require_owner` dependency. It validates the session cookie (`401` if missing, unknown, expired, or the user is disabled) and, for unsafe methods, the CSRF header (`403`).
- The only public endpoints are `GET /api/health`, `POST /api/auth/login`, and `GET /api/auth/session` (which reports `authenticated: false` without a valid session and exposes nothing private).
- A test enumerates every registered route and asserts that anything not on the public list rejects unauthenticated requests with `401`.
- The frontend's route guard is a convenience only. The API never relies on it.

### 8. Login throttling

- An in-memory, per-process limiter counts **failed** logins per client IP: 10 failures in a sliding 15-minute window → `429` until the window clears. It doesn't key on username, so it doesn't reveal which usernames exist. A successful login doesn't reset other clients.
- Limits: it resets on restart and isn't shared across processes; behind a reverse proxy every client may share the proxy's IP unless the proxy's forwarded address is trusted (it isn't configured to be).
- **Production deployment is blocked until login rate limiting is reviewed** together with the hosting topology (proxy headers, process count, persistent or shared counters). The authentication design is not claimed to be Internet-production-ready.

### 9. API error model

- Errors use FastAPI's standard shape: `{"detail": "<message>"}` for HTTP errors and `{"detail": [{"loc", "msg", "type"}, ...]}` for validation errors (`422`). The validation handler drops the echoed `input`/`ctx`, so a rejected login never echoes a password.
- Database integrity conflicts map to `409` with a generic message. Unexpected errors map to `500` `{"detail": "Internal server error."}`, logged server-side without request bodies. SQL, stack traces, hashes, and tokens are never returned.

## Consequences

- Owner creation and password rotation need shell access to the backend environment. That's deliberate for a single-user tool.
- Absolute session expiry means re-login at least every `SESSION_TTL_HOURS`.
- Login throttling is local-only (see §8). Hosted deployment needs a follow-up review.
- A future multi-user design (not planned) would need ownership columns and a new ADR.

## Alternatives Considered

- **Hosted identity (Auth0, Clerk, Supabase Auth, Google sign-in).** Free tiers exist, but they add an external dependency, account setup, and possible billing changes for one user. Rejected per ADR-004.
- **JWT in `localStorage`.** Readable by any injected script and can't be revoked server-side without extra state. Rejected.
- **Signed stateless cookie sessions.** Needs a signing secret to manage, and revocation needs server state anyway. Rejected in favor of opaque DB sessions.
- **Random CSRF token stored per session.** Also valid. To return it after a reload it would have to be stored readable (or in a JS-readable cookie). The HMAC-derived token gives the same guarantees without a stored secret.
- **Double-submit cookie.** Works, but a JS-readable cookie is an extra moving part compared with returning the token in the session response.
- **Redis/hosted rate limiter.** Adds a service for a single user. Deferred to the deployment review.
