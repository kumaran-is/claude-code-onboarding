# FastAPI Authorization Boundaries

Authentication proves who is calling (`fastapi-auth-security.md`). This file covers what that
caller may do: which identity an action is attributed to, which objects it may touch, which
endpoints only machines may call, and how to test the refusals. The §1, §2, §3 (shared secret),
§4, §6 and §9 snippets were executed on Python 3.14.10 / FastAPI 0.165.0 / Starlette 1.10.0 /
Pydantic 2.14.4 / SQLAlchemy 2.1.9 / asyncpg 0.32.0 against PostgreSQL 18.7 (16 tests via httpx2
2.16.2; removing the scope predicate, `extra="forbid"`, the fail-closed check or the empty-secret
guard each turned its tests red). §3 machine callers, §10, §11 and §12 ran on the same Python/FastAPI
with google-auth 2.63.1, cachecontrol 0.15.0 and httpx 0.28.1 (no database). §5, §7 and §8 are rules
without code.

> **Authenticated is not authorised.** A valid JWT answers "who"; every route still needs
> "may this actor do this to this object, and is the action allowed for end users at all".
> A role check on the route (`require_role`) is necessary but never sufficient.

| Question per route | Control |
|--------------------|---------|
| Whose identity is the action attributed to? | Actor id comes from the verified token (§1) |
| Which object is touched? | Scope predicate in the query; 404 for missing and foreign alike (§2) |
| Is this endpoint for end users at all? | Service credential for side-effect endpoints (§3) |
| Is the caller eligible, not only the owner? | Approval/eligibility check, fail closed (§4) |
| Does a response reveal who exists? | Identical status and body (§5) |
| What does a brand-new identity get? | No roles (§6) |

---

## 1. Actor vs subject

The **actor** is the caller. Its id comes from the verified token, never from the body. A body field
naming a role the caller holds is a forgery vector. The **subject** (who or what the action is
about) may arrive in the body, with an authorization check. Pass the derived actor id to the
service as its own explicit argument. Request models set `extra="forbid"`, so a smuggled
`author_id` is a 422, not a silently ignored key.

```python
class CreateDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID      # SUBJECT: needs an authorization check (§2)
    title: str              # no author_id / owner_id: the actor is the caller

@app.post("/documents", status_code=201)
async def create_document(body: CreateDocument, session: SessionDep, user: UserDep):
    ...
    return await service.create(body, author_id=user.id)    # explicit argument, never read off body
```

Executed: a body containing `author_id` returned 422; the stored author was the token's id.
If an actor id must stay optional for backward compatibility: derive it when absent, and reject
when the caller holds the actor role and the supplied id differs from their own.

---

## 2. Object-level scope — an FK proves existence, not permission

Filter by the caller's scope **in the query** and answer 404 for missing and foreign alike (a 403
for "exists but not yours" is an existence oracle).

```python
def visible_to(user_id: UUID) -> ColumnElement[bool]:
    """ONE shared predicate per relationship. No expiry/soft-delete check: writes add their own."""
    return exists().where(Membership.workspace_id == Workspace.id, Membership.user_id == user_id)


ws = await session.scalar(
    select(Workspace).where(Workspace.id == workspace_id, visible_to(user.id))
)
if ws is None:
    raise NotFound  # same status and body for a missing id and a foreign id
```

| Rule | Detail |
|------|--------|
| One predicate module | Copies drift, and drift is a security bug |
| Document what it does not check | Linkage vs currency (expired, soft-deleted); each write path adds its own filter |
| On create | Verify the caller is linked to every referenced parent; the FK alone only proves it exists |
| Admin bypass | Scope-bound too (an admin of one organization is not an admin of all) |
| Recipients of notifications | Resolve through the same current-relationship rule, not from history |

WRONG (existence oracle, scope checked after the fetch):

```python
doc = await service.get(doc_id)
if doc is None: raise HTTPException(404)
if doc.owner_id != user.id: raise HTTPException(403)    # confirms the document exists
```

---

## 3. Side-effect endpoints are for services, not users

Endpoints that cause effects for third parties (send email/SMS/push, move money, call a metered
API) must be callable only with a **service credential**, never with any end-user JWT.
The `/internal/` prefix is a naming convention; the guard is the control. A caller-chosen
recipient on a verified sender domain is a phishing relay.

```
Side-effect endpoint?
 [ ] callable only with a service credential (shared-secret dependency or platform identity token)
 [ ] recipient resolved server-side from an id; a caller-supplied address is refused before the send
 [ ] preference/consent gate runs on every path including fallbacks
 [ ] tests: user JWT -> 401/403; mismatched recipient -> refused; no send call recorded
```

Shared-secret guard: `require_internal_secret` in `backend-service-patterns.md` P1 (timing-safe
compare on bytes; `internal_api_secret: SecretStr = Field(min_length=32)`, so an empty secret fails
at boot — `hmac.compare_digest(b"", b"")` is `True`). Executed: absent, empty, wrong and non-ASCII
header → 403, correct → 200; `Settings(internal_api_secret="")` raised.

**Machine callers** (scheduler, queue push, cross-service calls) should present the platform's
signed identity token: verify signature, audience and the expected caller identity; fail startup
when the expected identity is unset in any deployed environment (an unwired config makes the gate
dead in production). Local/test environments may use the shared secret. Never leave the endpoint
unauthenticated.

Google-signed OIDC tokens (Pub/Sub push with an authenticated subscription, Cloud Scheduler, Cloud
Run service-to-service) with `google-auth` 2.63:

```python
import functools

import anyio, anyio.to_thread, cachecontrol, requests   # pin: cachecontrol==0.15.0 (vetted below)
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

def make_google_request(timeout: float = 5) -> functools.partial[google_requests.Request]:
    # google-auth re-downloads Google's certificates on EVERY verify unless the session caches them;
    # CacheControl honours the response's max-age. The transport's default timeout is 120 s.
    return functools.partial(
        google_requests.Request(session=cachecontrol.CacheControl(requests.Session())), timeout=timeout)

_google_request = make_google_request()
_google_threads = anyio.CapacityLimiter(4)       # cert checks never hold more than 4 worker threads

def google_service_dep(*, audience: str, allowed_emails: frozenset[str]):
    if not audience or not allowed_emails:
        raise ValueError("audience and allowed_emails are required")

    async def _dep(cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
        if cred is None:
            raise unauthorized()
        try:
            claims = await anyio.to_thread.run_sync(
                id_token.verify_oauth2_token, cred.credentials, _google_request, audience, 30,
                limiter=_google_threads)
        except google_exceptions.TransportError as exc:
            log.error("google_certs_unavailable", error_type=type(exc).__name__)
            raise HTTPException(503, "Authentication unavailable") from exc
        except (ValueError, google_exceptions.GoogleAuthError) as exc:
            raise unauthorized() from exc
        # ANY Google-signed token minted for this audience verifies: pin the caller too
        if claims.get("email") not in allowed_emails or claims.get("email_verified") is not True:
            raise HTTPException(403, "Caller not allowed")
        return claims["email"]
    return _dep
```

`verify_oauth2_token` checks signature, `exp`/`iat` (with the skew given, ≤ 60 s sensible), `aud`
and `iss ∈ {accounts.google.com, https://accounts.google.com}`. `audience` is the exact value set on
the push subscription or scheduler job (often the endpoint URL). Executed with Google's certificate
download stubbed by a local key (SDK checks ran; not live validation): foreign `aud` → 401, foreign
`iss` → 401, another service account → 403, `email_verified: false` → 403, no token → 401; removing
the email pin or passing `audience=None` turned the matching tests red. Against a local certificate
server (`cachecontrol` 0.15.0, `Cache-Control: max-age=300`): five verifications made one download
(without CacheControl: five); a server stalling 3 s gave 503 within 2.5 s at a 1 s timeout. `cachecontrol`
was vetted per `security-reviewer` checklist §6: published from the PSF's `psf/cachecontrol`
repository with a PyPI Trusted Publishing attestation (`release.yml`), ~26 M downloads a week, steady
release history (0.14.4 on 2025-11-14, 0.15.0 on 2026-11-16). Pin it exactly; review the next bump.

Calling another service: `id_token.fetch_id_token(google_requests.Request(), target_audience)` gets
the token from the metadata server on Cloud Run/GCE, or from a `service_account` /
`impersonated_service_account` file named by `GOOGLE_APPLICATION_CREDENTIALS`; plain user ADC from
`gcloud auth application-default login` is not accepted (google-auth 2.63 source). It is blocking;
run it in a thread and cache until shortly before `exp`. Live call: NOT RUN (no service identity in
the test environment).

---

## 4. Ownership is not eligibility

A route that lets a user grant a privilege to a third party must also check the **grantor's
approval status**, not only that they own the resource.

- Fail closed: only the explicit pass state passes (`status is Approval.APPROVED`); a member added to
  the enum later is denied by default. Never write `status != Approval.REJECTED`.
- Re-check at redemption (TOCTOU): approval can be revoked between grant and use.
- Record included **and** excluded routes with a reason. Some routes must stay open or approval
  deadlocks (the route that performs the approval itself).

```python
def may_grant(status_: Approval) -> bool:
    return status_ is Approval.APPROVED
```

---

## 5. Existence oracles

Distinct responses for "already registered" (409), "email conflict" or 403-vs-404 let anyone
enumerate accounts.

| Endpoint | Do |
|----------|----|
| Register | Same status/body whether or not the email exists; deliver the real outcome by email; log the real cause at error level for the operator |
| Login | One 401 for unknown user and wrong password; always run one hash verify (`fastapi-auth-security.md` §2) |
| Password reset | Same response and similar timing either way |
| Inbound identity (JIT) | Never auto-link to an existing row because a token merely claims its email |
| Object fetch | 404 for missing and foreign (§2) |

A uniqueness constraint still exists in the database; only the HTTP answer is uniform.

---

## 6. First-seen identities and roles

Signing in authenticates; it does not authorise. A just-in-time provisioned account is created
**role-less**; roles are granted only by a verified acquisition (invite, admin grant).

- Roles are a **set** in the claims object, populated from the database; avoid a single
  `user.role` plus a rank ladder when a user can hold several.
- FastAPI caches a dependency's result **per request**. A second dependency that mutates the
  returned object in place changes what every other consumer sees. Return a copy; never narrow
  roles in place, and never mutate an ORM collection with delete-orphan cascade.

```python
async def narrowed_in_place(c: ClaimsDep) -> list[str]:
    c["roles"] = ["member"]                                   # WRONG: shared cached object
    return c["roles"]

async def narrowed_copy(c: ClaimsDep) -> list[str]:
    return [r for r in c["roles"] if r == "member"]           # RIGHT: derive a new value
```

Executed: the in-place variant made the handler see `{"roles": ["member"]}` (admin lost);
the copy left `["admin", "member"]` intact.

---

## 7. Public and pre-acceptance lookups

Lookups reachable before the caller has a relationship (invite validation, share links) return the
**minimum**: drop owner contact fields. Bound enumeration of low-entropy codes per user with a
database-backed attempt cap in addition to the rate limiter, and key limits on the authenticated
user id, not the IP (`fastapi-rate-limiting.md`).

---

## 8. Refresh tokens

A self-issued refresh token that is a stateless 7-day JWT cannot be revoked or rotated. Either
delegate to a managed identity provider, or add `jti`, server-side storage, rotation and reuse
detection. Do not describe a stateless refresh JWT as "secure session management".

---

## 9. Evaluation order and tests

FastAPI resolves an auth dependency before body validation: bad body + missing/invalid token =
**401**, not 422. An optional header (`str | None = Header(None)`) yields 403 on absence; a
required header yields 422. Write expectations accordingly (`backend-live-e2e-standard.md`).

Authorization tests assert the **reason**, not just the status (an ownership 403 satisfies a bare
`== 403`), cover every non-pass state in a parametrized table, and prove the control is real with an
inert-not-deleted control (neutralize the check; the refusal tests must go red).

```python
@pytest.mark.parametrize("state", [s for s in Approval if s is not Approval.APPROVED])
def test_every_non_pass_state_is_refused(state):
    assert may_grant(state) is False


async def test_foreign_and_missing_are_indistinguishable(client, foreign_id):
    other, missing = (
        await client.get(f"/workspaces/{foreign_id}"),
        await client.get(f"/workspaces/{uuid4()}"),
    )

    def verdict(resp: httpx2.Response) -> tuple[int, str, str]:
        # envelope: timestamp, path, requestId and details.id differ by design
        body = resp.json()
        return resp.status_code, body["code"], body["message"]

    assert verdict(other) == verdict(missing) == (404, "NOT_FOUND", "Workspace not found")
```

---

## 10. Fetching user-supplied URLs (SSRF)

Any feature that fetches a URL a caller supplied (webhook targets, link previews, "import from
URL", agent fetch tools) can be pointed at the metadata server or internal services. A hostname
string check is not a guard: resolve, classify every answer, connect to the vetted IP, re-validate
each redirect.

```python
import asyncio, ipaddress, socket
from urllib.parse import urljoin, urlsplit
import httpx

_NAT64 = ipaddress.ip_network("64:ff9b::/96")

def is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Python 3.13+ classifies ::ffff:a.b.c.d by the embedded IPv4; NAT64 still needs unwrapping
    if isinstance(ip, ipaddress.IPv6Address) and ip in _NAT64:
        ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.is_global and not ip.is_multicast

async def safe_get(client: httpx.AsyncClient, url: str, *, max_redirects: int = 3,
                   max_bytes: int = 1_000_000, deadline_seconds: float = 10) -> bytes:
    """client: httpx.AsyncClient(follow_redirects=False, timeout=5) — a per-read timeout, not a total."""
    async with asyncio.timeout(deadline_seconds):   # a slow-drip server cannot hold the request open
        return await _fetch(client, url, max_redirects, max_bytes)

async def _fetch(client: httpx.AsyncClient, url: str, max_redirects: int, max_bytes: int) -> bytes:
    for _ in range(max_redirects + 1):
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise BlockedUrl("only https URLs without credentials")
        port = parts.port or 443
        infos = await asyncio.get_running_loop().getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
        ips = [ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos]
        if not ips or not all(is_public(ip) for ip in ips):      # one private answer poisons the set
            raise BlockedUrl("destination not allowed")
        host = f"[{ips[0]}]" if ips[0].version == 6 else str(ips[0])
        pinned = parts._replace(netloc=f"{host}:{port}").geturl()
        # connect to the vetted IP (no second lookup to rebind); TLS still verifies the real name
        req = client.build_request("GET", pinned, headers={"Host": parts.netloc},
                                   extensions={"sni_hostname": parts.hostname})
        resp = await client.send(req, stream=True)
        try:
            if resp.is_redirect:
                url = urljoin(url, resp.headers["location"])      # re-validated next pass
                continue
            resp.raise_for_status()
            body = bytearray()
            async for chunk in resp.aiter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    raise BlockedUrl("response too large")
            return bytes(body)
        finally:
            await resp.aclose()
    raise BlockedUrl("too many redirects")
```

Executed (httpx 0.28.1, Python 3.14.10, local HTTPS server, injected resolver): refused before
connecting — `http:`, `file:`, credentials in URL, `169.254.169.254`, a name answering one public and
one private address, `::1`, `::ffff:127.0.0.1`, `127.0.0.1`, `2130706433`, `10.1.2.3`,
`64:ff9b::7f00:1` (NAT64 of loopback, which `is_global` alone reports as global); a redirect to the
metadata address and an https→http redirect refused; a 2 MB body cut at 1 MB; a certificate for
another name failed TLS; a server dripping one byte every 0.2 s hit the total deadline
(`TimeoutError` at 1 s; without `asyncio.timeout` it ran to completion). Each check has a mutation that turned its test red. Add an egress proxy or
firewall allowlist where the platform offers one; this guard is the application layer.

---

## 11. CORS and CSRF

| API style | CSRF exposure | Control |
|-----------|---------------|---------|
| Bearer token in `Authorization` | None (no ambient credential) | CORS allowlist only |
| Cookie session | Yes | `SameSite=Lax`/`Strict`, `Secure`, `__Host-` prefix, **plus** an `Origin` check and a double-submit token on unsafe methods |

```python
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,   # validated list of exact origins
                   allow_credentials=settings.cookie_sessions,           # False for bearer-token APIs
                   allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"])

async def require_csrf(request: Request,
                       csrf_cookie: Annotated[str | None, Cookie(alias="__Host-csrf")] = None,
                       csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise HTTPException(403, "Cross-site request refused")
    # bytes: compare_digest raises TypeError on non-ASCII str (a 500, not a 403)
    if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie.encode(), csrf_header.encode()):
        raise HTTPException(403, "CSRF check failed")
```

Executed (Starlette 1.10): `allow_origins=["*"]` with `allow_credentials=True` **echoed
`https://evil.example.test`** with `Access-Control-Allow-Credentials: true` on a request carrying a
cookie; an explicit list omitted the header for a foreign origin. Missing header, mismatched token
and foreign `Origin` → 403; matching token → 200; a non-ASCII token → 403 (with `str` arguments:
`TypeError`). `cors_origins` must hold exact strings as browsers send them: typed `list[HttpUrl]`,
`https://app.example.test` became `https://app.example.test/` and matched neither CORSMiddleware nor
the Origin check; the `Origin` type in `env-config-validation.md` refuses `*`, paths and trailing
slashes. Webhook routes (signed by the sender) are exempt
from CSRF, not from signature checks (`stripe` skill, Security section).

---

## 12. Roles and permissions

Roles are a **set** populated from the database (a user may hold several). New accounts have no
roles (§6).

```python
from collections.abc import Awaitable, Callable


class Role(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"

_RANK = {Role.VIEWER: 0, Role.EDITOR: 1, Role.ADMIN: 2}          # higher = more access

def require_role(minimum: Role) -> Callable[[User], Awaitable[User]]:
    async def _check(user: CurrentUserDep) -> User:
        if max((_RANK[r] for r in user.roles), default=-1) < _RANK[minimum]:
            # do not echo role names
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user
    return _check

@router.delete("/users/{user_id}", dependencies=[Depends(require_role(Role.ADMIN))])
async def delete_user(user_id: UUID) -> None: ...
```

Executed: role-less, viewer and viewer+editor → 403 on an admin route; admin → 200; no token → 401.
A role check does not authorise object access — add the scope predicate (§2).

### Permissions (PBAC)

Map roles to permissions once; guard routes by permission. A role-less user has an empty union and is denied.

```python
class Permission(StrEnum):
    READ_REPORTS = "read:reports"
    WRITE_REPORTS = "write:reports"
    MANAGE_USERS = "manage:users"

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.READ_REPORTS}),
    Role.EDITOR: frozenset({Permission.READ_REPORTS, Permission.WRITE_REPORTS}),
    Role.ADMIN: frozenset(Permission),                       # all permissions
}

def require_permission(permission: Permission) -> Callable[[User], Awaitable[User]]:
    async def _check(user: CurrentUserDep) -> User:
        granted = set().union(*(ROLE_PERMISSIONS.get(r, frozenset()) for r in user.roles))
        if permission not in granted:                        # no roles -> empty union -> denied
            # do not echo names
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing permission")
        return user
    return _check

@router.get("/reports", dependencies=[Depends(require_permission(Permission.READ_REPORTS))])
async def list_reports() -> list[ReportResponse]: ...
```

Executed: editor reads (200) but cannot manage users (403); a role-less user is denied (403); admin
passes. Disabling either check turned the table red.
Prefer permissions over role comparisons once more than three roles exist.

---

## Reviewer checklist

```
□ Actor id from the token; request models extra="forbid"; no actor id in any body
□ Every fetch-by-id carries a scope predicate; foreign == missing (404)
□ Create verifies the caller's link to each referenced parent
□ Side-effect endpoints require a service credential; recipient resolved server-side
□ Grants check grantor eligibility, fail closed, re-checked at use
□ No endpoint answers differently for existing vs non-existing accounts
□ New identities start role-less; dependency results are copied before narrowing
□ Tests assert the reason, cover every non-pass state, include an inert control
□ Machine-caller tokens: audience AND caller email pinned; empty allowlist refused at startup
□ User-supplied URLs go through the SSRF guard (resolve, classify all answers, pin, per-hop redirects, size cap)
□ CORS origins exact strings (no "*", no trailing "/"); credentials only for cookie sessions, which add Origin check + double-submit token
□ SSRF fetch has a total deadline (asyncio.timeout), not only a per-read timeout
```

Severity guide: CRITICAL = end-user JWT can trigger a send/charge endpoint, or an admit-all
guard; HIGH = actor id from body, unscoped object fetch, commit-after-yield. A green pattern gate
does not prove any of these guarantees: route auth, rate-limit and approval changes to
`security-reviewer` regardless.
