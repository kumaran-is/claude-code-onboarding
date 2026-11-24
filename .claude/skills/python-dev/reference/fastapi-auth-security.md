# FastAPI Auth & Security Patterns

Authentication and role-based access for Python 3.14 + FastAPI. Everything uses FastAPI
`Depends()` — no middleware monkey-patching. Object scope, actor vs subject, service-only
endpoints and existence oracles live in `fastapi-authorization-boundaries.md`.

> Executed on Python 3.14.10, FastAPI 0.165.0, Starlette 1.10.0, PyJWT 2.15.1, pwdlib 0.4.2,
> firebase-admin 7.8.0, google-auth 2.63.1 (tests driven through httpx2 2.16.2).
> **Libraries:** PyJWT + pwdlib are what FastAPI's current OAuth2/JWT tutorial uses.
> `python-jose` and `passlib` are **not** used in new code (reject in review; migrate existing code):
> - `python-jose` 3.5.0 (last release 2025-05-28) has an unpatched **critical** advisory,
>   GHSA-3qf3-8w2g-rqmx / CVE-2026-85394 (algorithm-confusion guard bypassed by DER-encoded public
>   keys; affected `<= 3.5.0`, no fixed version), and hard-depends on `ecdsa`, whose Minerva timing
>   advisory CVE-2024-23342 also has no fix.
> - `passlib` 1.7.4 fails on first hash with `bcrypt` 5.0.0 (version-detect trap, then `ValueError`).
>   1.9.5 (2026-11-23, after 6 years dormant) works with bcrypt 5 but publishes from a different
>   repository: treat it as a new, unvetted dependency (`security-reviewer` checklist §6).
>
> Also checked: `joserfc` 1.8 (no JWKS fetcher; fine when you need JWE), `Authlib` 1.9 (heavier than a
> resource server needs). Keys are fetched with async httpx (§3a), not the blocking `PyJWKClient`.

| python-jose | PyJWT |
|-------------|-------|
| `from jose import jwt, JWTError` | `import jwt` (errors: `jwt.PyJWTError`, `jwt.InvalidTokenError`) |
| `jwt.decode(t, key, algorithms=[...], audience=a, issuer=i)` | same call; add `options={"require": [...]}` and `leeway=` |
| `jwk.construct(jwks_key)` | `jwt.PyJWK(dict)`; a fetched set: `jwt.PyJWKSet.from_dict(json)` (§3a) |
| `ExpiredSignatureError`, `JWTClaimsError` | `jwt.ExpiredSignatureError`, `jwt.InvalidAudienceError`, `jwt.InvalidIssuerError`, `jwt.MissingRequiredClaimError` |

---

## Dependencies

```bash
uv add pyjwt "pwdlib[argon2]" python-multipart "pydantic[email]"
# pyjwt[crypto] for RS256/ES256; python-multipart is required by OAuth2PasswordRequestForm;
# pydantic[email] installs email-validator, which EmailStr (RegisterRequest) needs
```

```toml
dependencies = ["pyjwt==2.15.1", "pwdlib[argon2]==0.4.2"]   # versions executed for this guide; pin what your lockfile resolves
```

---

## 1. Configuration

Fields join the fail-fast `Settings` from `fastapi-architecture-and-config.md` §2:

```python
jwt_secret: SecretStr = Field(min_length=32)   # no default; HS256 needs a long random key
jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"   # "none" or an RS* typo fails at boot
jwt_issuer: str                                # no default
jwt_audience: str                              # no default
access_token_expire_minutes: int = 15
```

HS256 suits a single service that both issues and verifies. For tokens verified by other services
use RS256/ES256 (`pyjwt[crypto]`) so verifiers hold only the public key.

---

## 2. Password hashing (async, timing-safe)

Hashing is CPU-bound (Argon2id ~20 ms, bcrypt cost 12 ~180 ms on one local sample): run it in a thread
pool, or every login stalls the event loop. For an unknown account still verify against a dummy
hash so response time does not reveal whether the account exists.

```python
# src/my_service/core/security.py
from pwdlib import PasswordHash
from starlette.concurrency import run_in_threadpool

_hasher = PasswordHash.recommended()                  # Argon2id
_DUMMY_HASH = _hasher.hash("timing-equaliser")        # computed once at import

async def hash_password(plain: str) -> str:
    return await run_in_threadpool(_hasher.hash, plain)

async def verify_password(plain: str, stored: str | None) -> bool:
    """Always runs one verify, so response time does not reveal whether the account exists."""
    ok = await run_in_threadpool(_hasher.verify, plain, stored or _DUMMY_HASH)
    return ok and stored is not None
```

Executed: unknown account 19.3 ms vs wrong password 19.2 ms; 4 concurrent hashes left the event loop
ticking. Request models bound password length (`max_length=128`) so hashing cost cannot be abused.

**Legacy bcrypt hashes:** `PasswordHash((Argon2Hasher(), BcryptHasher()))` verifies both and
`verify_and_update(plain, stored)` returns `(ok, new_hash | None)` — store `new_hash` on login to
migrate (needs `pwdlib[argon2,bcrypt]`).

**Rule:** never store, log or return plaintext passwords. Passwords are `SecretStr` in request models.

---

## 3. JWT token service

```python
# src/my_service/core/tokens.py
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

def create_access_token(subject: str, *, minutes: int = 15) -> str:
    now = datetime.now(UTC)
    claims = {"sub": subject, "type": "access", "iss": ISSUER, "aud": AUDIENCE,
              "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(claims, JWT_SECRET, algorithm=ALGORITHM)

def decode_token(token: str) -> dict[str, Any]:
    """Raises jwt.InvalidTokenError (base class of every validation failure)."""
    return jwt.decode(
        token, JWT_SECRET, algorithms=[ALGORITHM],      # explicit; never derived from the token header
        audience=AUDIENCE, issuer=ISSUER,
        options={"require": ["exp", "sub", "iat"]},    # without it a token with no exp never expires
    )
```

`JWT_SECRET` etc. come from `Settings` (`settings.jwt_secret.get_secret_value()`). Executed: a token
with no `exp` **decoded** with plain `jwt.decode(...)`; `require` raised `MissingRequiredClaimError`,
wrong `aud` `InvalidAudienceError`, expired `ExpiredSignatureError`, `alg: none` `InvalidTokenError`.

Refresh tokens: a stateless 7-day JWT cannot be revoked or rotated. Delegate to a managed identity
provider, or add `jti`, server-side storage, rotation and reuse detection (`fastapi-authorization-boundaries.md` §8).

### 3a. Tokens from an identity provider (JWKS, RS256/ES256)

A resource server holds no signing key: it fetches the issuer's public keys (JWKS) over HTTPS.
Fetch them with the async httpx client (no worker thread), share one refresh between concurrent
requests, keep the last good set for a bounded time while the IdP is down, and allow at most one
fetch attempt per cooldown so unknown-`kid` floods cannot hammer the IdP.

```python
# src/my_service/core/idp_tokens.py
import asyncio, math, time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx, jwt, structlog

log = structlog.get_logger(__name__)
_ASYMMETRIC = frozenset({"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "EdDSA"})

@dataclass(frozen=True, slots=True)
class JwtPolicy:
    jwks_url: str
    issuer: str
    audience: str                                   # this API's identifier, exactly
    algorithms: tuple[str, ...] = ("RS256",)
    leeway_seconds: int = 30
    required: tuple[str, ...] = ("exp", "iat", "iss", "aud", "sub")
    expected_typ: str | None = "at+jwt"             # RFC 9068 access tokens; None if your IdP omits typ
    strict_aud: bool = True                         # aud must be one string equal to audience
    jwks_ttl_seconds: float = 300                   # refresh a good set this often
    jwks_cooldown_seconds: float = 30               # at most one fetch attempt per window
    jwks_max_stale_seconds: float = 3600            # serve the last good set this long during an outage

class JwksUnavailable(Exception):
    """IdP down and no usable key set: 503, not 401."""

class TokenVerifier:
    def __init__(self, policy: JwtPolicy, client: httpx.AsyncClient, *, clock=time.monotonic) -> None:
        if urlsplit(policy.jwks_url).scheme != "https":
            raise ValueError("JWKS URL must use https")
        if not policy.algorithms or not set(policy.algorithms) <= _ASYMMETRIC:
            raise ValueError("pin asymmetric algorithms only")
        self._p, self._client, self._clock = policy, client, clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = self._attempted_at = -math.inf
        self._lock = asyncio.Lock()                 # single flight

    async def _refresh(self, seen_fetch: float) -> None:
        async with self._lock:
            now = self._clock()
            if self._fetched_at != seen_fetch or now - self._attempted_at < self._p.jwks_cooldown_seconds:
                return                              # refreshed meanwhile, or tried too recently
            self._attempted_at = now
            try:
                async with asyncio.timeout(5):      # total deadline
                    resp = await self._client.get(self._p.jwks_url)
                    resp.raise_for_status()
                    keyset = jwt.PyJWKSet.from_dict(resp.json())
            except (httpx.HTTPError, TimeoutError, ValueError, jwt.PyJWTError) as exc:
                log.error("jwks_refresh_failed", error_type=type(exc).__qualname__)
                return                              # keep the last good set; _key() judges its age
            usable = (k for k in keyset.keys if k.key_id and k.public_key_use in (None, "sig"))   # no "enc" keys
            self._keys, self._fetched_at = {k.key_id: k for k in usable}, now

    async def _key(self, kid: str) -> jwt.PyJWK:
        if kid not in self._keys or self._clock() - self._fetched_at >= self._p.jwks_ttl_seconds:
            await self._refresh(self._fetched_at)
        if not self._keys or self._clock() - self._fetched_at >= self._p.jwks_max_stale_seconds:
            raise JwksUnavailable
        if (key := self._keys.get(kid)) is None:
            raise jwt.InvalidTokenError("unknown kid")
        return key

    async def verify(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in self._p.algorithms:      # before any JWKS fetch
            raise jwt.InvalidAlgorithmError("algorithm not allowed")
        typ = self._p.expected_typ
        if typ and str(header.get("typ", "")).lower() not in {typ, f"application/{typ}"}:
            raise jwt.InvalidTokenError("unexpected typ")    # an ID token is not an access token
        if not isinstance(kid := header.get("kid"), str):
            raise jwt.InvalidTokenError("missing kid")
        key = await self._key(kid)
        return jwt.decode(                                   # CPU only: fine on the event loop
            token, key, algorithms=list(self._p.algorithms),
            audience=self._p.audience, issuer=self._p.issuer, leeway=self._p.leeway_seconds,
            options={"require": list(self._p.required), "strict_aud": self._p.strict_aud,
                     "enforce_minimum_key_length": True},
        )
```

The dependency (one core for HTTP and WebSocket; `HTTPConnection` and `HTTPBearer(auto_error=False)`
work for both, and a missing header is your 401, not a 403):

```python
from fastapi import Depends, HTTPException, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import HTTPConnection

BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))]

class _Rejected(Exception):
    def __init__(self, unavailable: bool) -> None:
        self.unavailable = unavailable

async def _authenticate(conn: HTTPConnection, cred: HTTPAuthorizationCredentials | None) -> Principal:
    if cred is None:
        raise _Rejected(unavailable=False)
    try:
        claims = await conn.app.state.token_verifier.verify(cred.credentials)
    except JwksUnavailable as exc:                           # the IdP is down; the token is not proven bad
        log.error("jwks_unavailable")
        raise _Rejected(unavailable=True) from exc
    except jwt.PyJWTError as exc:
        log.info("token_rejected", reason=type(exc).__name__)    # never the token
        raise _Rejected(unavailable=False) from exc
    scope = claims.get("scope", "")
    return Principal(str(claims["sub"]), frozenset(scope.split()) if isinstance(scope, str) else frozenset(), claims)

async def get_principal(conn: HTTPConnection, cred: BearerDep) -> Principal:
    try:
        return await _authenticate(conn, cred)
    except _Rejected as exc:
        if exc.unavailable:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication unavailable") from exc
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"}) from exc

async def get_ws_principal(conn: HTTPConnection, cred: BearerDep) -> Principal:   # refused before accept()
    try:
        return await _authenticate(conn, cred)
    except _Rejected as exc:
        code = status.WS_1013_TRY_AGAIN_LATER if exc.unavailable else status.WS_1008_POLICY_VIOLATION
        raise WebSocketException(code, "Not authenticated") from exc

CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
```

Executed (32 tests; each check has a mutation that turned it red): alg `none`, HS256 signed with the
public PEM, wrong key under a known `kid`, expiry beyond leeway (10 s past `exp` accepted, 120 s
refused), future `nbf`, each required claim missing, foreign `aud`, `aud` list under `strict_aud`,
wrong `iss`, `typ: JWT`, `http://` JWKS URL, symmetric algorithm in the policy, unreachable JWKS →
503, ES256 policy vs RS256 token. Keys: a new `kid` verified after one refetch once the cooldown
passed; 20 unknown `kid`s inside it → zero fetches; 20 concurrent verifications on a cold cache → one
fetch (without the lock: 503s); IdP returning 500 → the last good set kept verifying past the TTL,
then 503 after `jwks_max_stale_seconds`; no worker thread borrowed; a `use: "enc"` key → 401, a key
without `use` verified. WebSocket: valid token accepted;
none, garbage, expired → 1008.

**Browsers cannot set `Authorization` on a WebSocket.** Issue a single-use ticket from an
authenticated HTTP call and redeem it before `accept()`:

```python
async def issue_ws_ticket(request: Request, principal: CurrentPrincipal) -> dict[str, str | int]:
    ticket = secrets.token_urlsafe(32)
    await request.app.state.redis.set(f"ws-ticket:{ticket}", principal.subject, ex=30)
    return {"ticket": ticket, "expires_in": 30}      # browser opens wss://…/ws?ticket=<ticket>

async def ws_ticket_subject(websocket: WebSocket, ticket: Annotated[str | None, Query()] = None) -> str:
    if websocket.headers.get("origin") not in websocket.app.state.allowed_origins:
        raise WebSocketException(status.WS_1008_POLICY_VIOLATION, "Origin not allowed")
    # GETDEL is atomic: the ticket is in the URL (and access logs), so it must die on first use
    subject = await websocket.app.state.redis.getdel(f"ws-ticket:{ticket}") if ticket else None
    if subject is None:
        raise WebSocketException(status.WS_1008_POLICY_VIOLATION, "Not authenticated")
    return subject.decode() if isinstance(subject, bytes) else subject   # str if decode_responses=True
```

Executed (Redis 8.2): second use, foreign `Origin`, missing, unknown and expired tickets → 1008;
`GET` for `GETDEL`, no Origin check or no TTL each turned a test red; `bytes` and `str` replies both work. Never put the access token in a URL.

Not `PyJWKClient` in `run_in_threadpool`: each fetch holds one of the 40 shared worker threads for up
to its timeout. Keep `strict_aud` on (PyJWT's default is off: an `aud` list naming your API passes).

### 3b. Firebase ID tokens

```python
from firebase_admin import auth, tenant_mgt

def _verify_firebase(token: str, app, tenant_id: str | None) -> dict:
    client = tenant_mgt.auth_for_tenant(tenant_id, app=app) if tenant_id else None
    if client:
        return client.verify_id_token(token, check_revoked=True, clock_skew_seconds=30)
    return auth.verify_id_token(token, app=app, check_revoked=True, clock_skew_seconds=30)

claims = await run_in_threadpool(_verify_firebase, token, firebase_app, settings.firebase_tenant_id)
```

Map `auth.CertificateFetchError` → 503; `auth.InvalidIdTokenError` (parent of Expired/Revoked),
`auth.UserDisabledError` and `tenant_mgt.TenantIdMismatchError` → 401. The SDK checks RS256, `kid`,
`aud` = project id, `iss` = `https://securetoken.google.com/<project>`, `sub`; `clock_skew_seconds`
is 0–60. `check_revoked=True` costs one Auth API lookup per call: use it on sensitive routes or cache
per token for seconds.

- **Multi-tenant:** `auth.verify_id_token` does **not** check the tenant. Executed: a token for tenant
  B passed the project-level call; `auth_for_tenant("tenant-a…")` refused it (401) and accepted A's.
- **Emulator bypass:** with `FIREBASE_AUTH_EMULATOR_HOST` set, firebase-admin skips signature checks.
  Executed: a token signed by an unknown key verified. Fail startup when it is set outside local/test
  (the `deployed_invariants` validator in `deployment-ci-cd/reference/env-config-validation.md`).

Executed with Google's certificate download stubbed by a local test key (the SDK's own claim and
signature checks ran; this is not live-provider validation): wrong project in `aud`/`iss`, expired,
empty `sub`, wrong key, HS256 → all 401. `check_revoked=True` against the live Auth API: NOT RUN (needs
project credentials).

---

## 4. OAuth2 bearer — current-user dependency

```python
# src/my_service/api/deps.py
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

async def get_current_subject(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    credentials_error = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_token(token)
    except jwt.InvalidTokenError as exc:
        # same 401 for every failure; log the type only
        raise credentials_error from exc
    if claims.get("type") != "access":
        raise credentials_error
    return str(claims["sub"])
```

Load the user (and roles) from the database in a second dependency keyed on the subject; a token
for a deleted or disabled account must fail. Catch `jwt.InvalidTokenError` only.

---

## 5. Auth routes

```python
@router.post(
    "/token",
    response_model=TokenResponse,
    # all attempts, up front: bounds the check-then-record race below (fastapi-rate-limiting.md §3)
    dependencies=[Depends(rate_limit("20/minute", scope="login", key=client_ip_key))],
)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    users: UserServiceDep,
    tenants: TenantServiceDep,
) -> TokenResponse:
    email = form.username.strip().lower()  # repo: func.lower(User.email) == func.lower(email)
    await check_login_failures(request, email)
    # email is unique per tenant: resolve the tenant first, exactly "<slug>.example.com"
    tenant_id = await tenants.id_for_host(request.url.hostname)  # None when unknown: same path
    user = await users.get_by_email(tenant_id, email) if tenant_id else None
    if (  # verify always runs (dummy hash for unknown tenant or email): no timing oracle
        not await verify_password(form.password, user.hashed_password if user else None)
        or user is None
        or not user.is_active  # disabled: the same 401
    ):
        await record_login_failure(request, email)  # failures only: no victim lockout
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(str(user.id)), token_type="bearer")


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(body: RegisterRequest, users: UserServiceDep) -> dict[str, str]:
    # no-op if it exists; identical answer either way
    await users.register(body.email, await hash_password(body.password.get_secret_value()))
    return {"message": "If the address is valid, check your email to continue"}
```

The tenant comes from `Host`, which the client sends: add `app.add_middleware(TrustedHostMiddleware,
allowed_hosts=["*.example.com"])` and match the host exactly. Registration answers the same whether
the email exists or not (409 = enumeration oracle); email the outcome, log the cause. Executed:
duplicate registrations → identical 202s; unknown user, unknown tenant (still hashing once), wrong
password, disabled account → identical 401s; one email in two tenants reached the right account; a
foreign Host → 400 before any lookup; nested `acme.evil.<domain>` matched no tenant. On PostgreSQL
18.7 with a `lower(email)` unique index, stored `Straße@…` matched `straße@…`/` STRAßE@… ` but not
`STRASSE@…`, exactly as the index decides (`casefold()` split from it). A global lookup, an early
401, `allowed_hosts=["*"]`, a suffix host match, no lowering, no `is_active` each turned a test red.

```python
class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)
```

---

## 6. RBAC — role-based access control

Roles are a set loaded from the database; new accounts have none. Code and tests:
`fastapi-authorization-boundaries.md` §12.

---

## 7. PBAC — permission-based access control

Map roles to permissions once and guard routes by permission (`require_permission`):
`fastapi-authorization-boundaries.md` §12.

---

## 8. Resource ownership

Never fetch by id and then compare owners (`doc = get(id); if doc.owner != user: 403`): that
confirms the object exists and the admin bypass is not scope-bound. Put the caller's scope in the
query and answer 404 for missing and foreign: `fastapi-authorization-boundaries.md` §2.

---

## 9. Rate limiting auth endpoints

`fastapi-rate-limiting.md`: `key=user_key` for enumeration surfaces, per-IP as an outer layer, and for
login **failed** attempts per (email, client IP), never a per-email lockout of a victim.

---

## 10. Security rules

| Rule | Detail |
|------|--------|
| **Hashing** | Argon2id via `pwdlib` (bcrypt only for legacy hashes, cost ≥ 12); run in a thread pool |
| **Token claims** | `require` `exp`, `sub`, `iat`; pin `algorithms`; check `aud`/`iss`; check `type == "access"` |
| **Token expiry** | Access ≤ 15 min; refresh tokens need server-side state to be revocable |
| **No plaintext** | Never log, store or return plaintext passwords or tokens |
| **401 vs 403** | 401 unauthenticated (with `WWW-Authenticate`); 403 authenticated but not permitted |
| **Account existence** | Same status/body for known and unknown accounts (login, register, reset) |
| **Order** | Auth dependency runs before body validation: bad body + no token = 401, not 422 |
| **HTTPS only** | `Secure` cookies; terminate TLS at a trusted proxy and set trusted proxy hosts explicitly |
| **IdP tokens** | JWKS over https fetched async (single flight, bounded stale grace, cooldown), asymmetric `algorithms` pinned, `typ` checked, `strict_aud`, leeway ≤ 60 s |
| **Review** | `from jose` in any code = HIGH (unpatched critical advisory); `passlib` = HIGH unless the new 1.9.x source was vetted; migrate to PyJWT / pwdlib |

---

## 11. Testing auth

Assert the **reason**, not only the status, and include the negative controls:

```python
async def test_login_success(client, seed_user):
    resp = await client.post(
        "/api/v1/auth/token", data={"username": seed_user.email, "password": "correct-password"}
    )
    assert resp.status_code == 200 and "access_token" in resp.json()

async def test_protected_route_no_token(client):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401 and resp.headers["www-authenticate"] == "Bearer"

async def test_token_without_exp_is_rejected(client):
    no_exp = jwt.encode({"sub": "u1", "iat": datetime.now(UTC)}, SECRET, algorithm="HS256")
    headers = {"Authorization": f"Bearer {no_exp}"}
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401

async def test_login_unknown_and_wrong_password_are_identical(client, seed_user):
    url = "/api/v1/auth/token"
    wrong = await client.post(url, data={"username": seed_user.email, "password": "wrong"})
    ghost = await client.post(url, data={"username": "ghost@example.com", "password": "wrong"})
    assert wrong.status_code == ghost.status_code == 401 and wrong.json() == ghost.json()
```

Also cover: expired token, wrong audience, missing `type`, no token (401). Authorization-specific
tests (every non-pass state, inert control): `fastapi-authorization-boundaries.md` §9.
