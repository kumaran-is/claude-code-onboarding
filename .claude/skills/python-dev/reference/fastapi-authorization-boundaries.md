# FastAPI Authorization Boundaries

Authentication proves who is calling (`fastapi-auth-security.md`). This file covers what that
caller may do: which identity an action is attributed to, which objects it may touch, which
endpoints only machines may call, and how to test the refusals. Snippets were executed on
FastAPI 0.165 / Pydantic 2.14 / SQLAlchemy 2.1 / PostgreSQL 16 (nothing needs newer than the 0.135 pin).

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

Shared-secret guard (empty secret refused at construction, timing-safe compare):
`backend-service-patterns.md` P1. Executed: empty/absent/wrong header → 403, correct → 200, and
`make_service_secret_dep("")` raises, because `hmac.compare_digest(b"", b"") is True`.

**Machine callers** (scheduler, queue push, cross-service calls) should present the platform's
signed identity token: verify signature, audience (when known) and the expected caller
identity; fail startup when the expected identity is unset in any deployed environment (an
unwired config makes the gate dead in production). Local/test environments may use the shared
secret. Never leave the endpoint unauthenticated. *Not executed here — check your platform's
token-verification library docs.*

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

    def verdict(resp: httpx.Response) -> tuple[int, str, str]:
        # envelope: timestamp, path, requestId and details.id differ by design
        body = resp.json()
        return resp.status_code, body["code"], body["message"]

    assert verdict(other) == verdict(missing) == (404, "NOT_FOUND", "Workspace not found")
```

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
```

Severity guide: CRITICAL = end-user JWT can trigger a send/charge endpoint, or an admit-all
guard; HIGH = actor id from body, unscoped object fetch, commit-after-yield. A green pattern gate
does not prove any of these guarantees: route auth, rate-limit and approval changes to
`security-reviewer` regardless.
