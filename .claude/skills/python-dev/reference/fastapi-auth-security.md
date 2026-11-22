# FastAPI Auth & Security Patterns

Authentication and role-based access for Python 3.14 + FastAPI. Everything uses FastAPI
`Depends()` — no middleware monkey-patching. Object scope, actor vs subject, service-only
endpoints and existence oracles live in `fastapi-authorization-boundaries.md`.

> Executed on FastAPI 0.165, PyJWT 2.15.1, pwdlib 0.4.2, Python 3.14; none of it needs more than the 0.135 pin.
> **Libraries:** PyJWT + pwdlib are what FastAPI's current OAuth2/JWT tutorial uses.
> `python-jose` and `passlib` are **not** used in new code (reject in review): the tutorial no
> longer shows them, and `passlib` 1.7.4 fails on first hash with `bcrypt` 5.0.0 (observed:
> version-detect trap, then `ValueError`).

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
jwt_algorithm: str = "HS256"
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
        token, JWT_SECRET,
        # explicit; never derived from the token header
        algorithms=[ALGORITHM],
        audience=AUDIENCE, issuer=ISSUER,
        # without this a token with no exp never expires
        options={"require": ["exp", "sub", "iat"]},
    )
```

(`JWT_SECRET` etc. come from `Settings`: `settings.jwt_secret.get_secret_value()`.)

Executed: a token with no `exp` **decoded successfully** with plain `jwt.decode(...)`; the
`require` option raised `MissingRequiredClaimError`. Wrong `aud` raised `InvalidAudienceError`,
an expired token `ExpiredSignatureError`, an `alg: none` token `InvalidTokenError`.

Refresh tokens: a stateless 7-day JWT cannot be revoked or rotated. Delegate to a managed identity
provider, or add `jti`, server-side storage, rotation and reuse detection (`fastapi-authorization-boundaries.md` §8).

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
@router.post("/token", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], users: UserServiceDep
) -> TokenResponse:
    user = await users.get_by_email(form.username)
    if (
        not await verify_password(form.password, user.hashed_password if user else None)
        or user is None
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(str(user.id)), token_type="bearer")


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(body: RegisterRequest, users: UserServiceDep) -> dict[str, str]:
    # no-op if it exists
    await users.register(body.email, await hash_password(body.password.get_secret_value()))
    # identical either way
    return {"message": "If the address is valid, check your email to continue"}
```

Registration answers identically whether or not the email exists (a 409 "already registered" is an
account-enumeration oracle); deliver the real outcome by email and log the cause for the operator.
Executed: two registrations of one address returned identical 202 bodies; unknown user and wrong
password returned identical 401 bodies.

```python
class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)
```

---

## 6. RBAC — role-based access control

Roles are a **set** populated from the database (a user may hold several). New accounts have no
roles (`fastapi-authorization-boundaries.md` §6).

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

Executed: a role-less user got 403, the same user with `ADMIN` got 200, no token got 401.
A role check does not authorise object access — add the scope predicate (`fastapi-authorization-boundaries.md` §2).

---

## 7. PBAC — permission-based access control

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

Executed: editor reads (200) but cannot manage users (403); a role-less user is denied (403); admin passes.
Prefer permissions over role comparisons once more than three roles exist.

---

## 8. Resource ownership

Never fetch by id and then compare owners (`doc = get(id); if doc.owner != user: 403`): that
confirms the object exists and the admin bypass is not scope-bound. Put the caller's scope in the
query and answer 404 for missing and foreign: `fastapi-authorization-boundaries.md` §2.

---

## 9. Rate limiting auth endpoints

Auth routes carry no path parameters, so `.limit()` works there, but enumeration surfaces (invite
codes, reset tokens by id) need `shared_limit(scope=...)` keyed on the user id — see
`fastapi-rate-limiting.md`. Starting points: login 5/minute, register 3/hour, password reset
3/hour (limit per email as well as per client). Per-IP keys are only an outer layer behind a proxy.

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
| **Review** | `from jose` or `passlib` in new code = reject |

---

## 11. Testing auth

Assert the **reason**, not only the status, and include the negative controls:

```python
@pytest.mark.asyncio
async def test_login_success(client, seed_user):
    resp = await client.post(
        "/api/v1/auth/token", data={"username": seed_user.email, "password": "correct-password"}
    )
    assert resp.status_code == 200 and "access_token" in resp.json()


@pytest.mark.asyncio
async def test_protected_route_no_token(client):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401 and resp.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_token_without_exp_is_rejected(client):
    no_exp = jwt.encode({"sub": "u1", "iat": datetime.now(UTC)}, SECRET, algorithm="HS256")
    assert (
        await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {no_exp}"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_and_wrong_password_are_identical(client, seed_user):
    wrong = await client.post(
        "/api/v1/auth/token", data={"username": seed_user.email, "password": "wrong"}
    )
    ghost = await client.post(
        "/api/v1/auth/token", data={"username": "ghost@example.com", "password": "wrong"}
    )
    assert (
        (wrong.status_code, wrong.json())
        == (ghost.status_code, ghost.json())
        == (401, wrong.json())
    )


@pytest.mark.asyncio
async def test_rbac_insufficient_role(client, viewer_token):
    resp = await client.delete(
        "/api/v1/users/some-id", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403 and resp.json()["message"] == "Insufficient role"
```

Also cover: expired token, wrong audience, missing `type`, no token (401). Authorization-specific
tests (every non-pass state, inert control): `fastapi-authorization-boundaries.md` §9.
