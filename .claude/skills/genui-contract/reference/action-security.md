# Action security: server-side handling of A2UI actions (v1.0 and v0.9)

> **Pins and proven wire version per platform:** see [compatibility-matrix.md](compatibility-matrix.md) (source of truth). Serve each client only the version it declares and is proven on. Every renderer and backend needs a contract gate in front of `@a2ui/web_core` (action allowlist, URL schemes, one version per stream, reject legacy `{"path"}` bindings in 1.0 with `SCHEMA_INVALID`), because web_core 0.16.1 and `@a2ui/agent` 0.2.1 accept these.

Generated UI is untrusted input. So is every action that comes back from it: the model wrote the surface, and the client (or an attacker) wrote the request. The server decides every action from the authenticated principal and its own data. Nothing in `action.context` grants permission.

Evidence: the code excerpts come from the reference backend's `genui_backend/actions.py`. Its 24 action tests pass. Removing the owner check makes the 403 test fail, and removing the idempotency store makes the duplicate and concurrency tests fail. **DOCUMENTED AND TESTED.**

## The pipeline (order matters)

Every gate runs before any side effect. The first failing gate decides the response.

| # | Gate | Failure |
|---|---|---|
| 1 | Bearer token: identity comes from the token, never the body | 401 `UNAUTHENTICATED` / `INVALID_TOKEN` + `WWW-Authenticate` |
| 2 | Bounded body read (16 KiB) | 413 `PAYLOAD_TOO_LARGE` |
| 3 | JSON, `version` present and equal to the version negotiated for this stream (`1.0` or `v0.9`) | 400 `INVALID_JSON` / `MALFORMED_MESSAGE` / `UNSUPPORTED_VERSION` |
| 4 | Official `client_to_server.json` schema (exactly `{version, action}`) | 400 `INVALID_MESSAGE` |
| 5 | Action name in the catalog allowlist (`x-genui.actions`) | 400 `UNKNOWN_ACTION` |
| 6 | **Rendered by us**: this server streamed a component to this user, on that `surfaceId`/`sourceComponentId`, that declares this action | 409 `NOT_RENDERED` |
| 7 | `context` against the action's `payloadSchema` (`additionalProperties: false`) | 422 `INVALID_PAYLOAD` |
| 8 | `Idempotency-Key` header when `requiresIdempotencyKey` (8-128 `[A-Za-z0-9_-]`; the contract suggests UUIDv4) | 400 `IDEMPOTENCY_KEY_REQUIRED` / `_INVALID`; 409 `IDEMPOTENCY_KEY_REUSED` |
| 9 | Resource authorization: tenant first, then owner or designated approver | 404 `NOT_FOUND` (absent or other tenant), 403 `FORBIDDEN` |
| 10 | Human approval for `requiresHumanApproval` | 202 `confirmation_required` + a server-authored ConfirmationDialog |
| 11 | Server re-validates every value the model offered (selection ids, form fields) | 422 `INVALID_SELECTION` / `UNKNOWN_FIELD` |
| 12 | Execute once, audit every decision | 200 |

## Catalog validation is not authorization

A message that passes catalog validation tells you the renderer can draw it. It says nothing about whether this user may perform the action it offers. Run both, and never treat the first as the second.

Evidence (Node 26 sandbox, `@a2ui/agent` 0.2.1 `validatePayload` against the shared 1.0 and v0.9 catalogs, **TESTED**):

| Sample | Contract expects | `validatePayload` |
|---|---|---|
| Unknown component | `UNKNOWN_COMPONENT` | rejected |
| Mixed versions in one payload | `MIXED_VERSIONS` | rejected |
| 1.0 `createSurface.theme` | `SCHEMA_INVALID` | rejected |
| Action name outside the catalog's enum | `ACTION_NOT_ALLOWED` | **accepted** |
| `javascript:` URL in a string | `UNSAFE_CONTENT` | **accepted** |
| v0.9 `{"path": ...}` binding inside a 1.0 message | `SCHEMA_INVALID` | **accepted** |

So the SDK check is a structural gate, not a policy gate. The server still needs: its own action allowlist, the forbidden-pattern scan, and per-action authorization. In the sandbox, an action outside the allowlist that the SDK accepted was refused with `403 ACTION_UNREGISTERED`, and removing the server's tenant check made the wrong-tenant test fail (negative control).

## Tenant isolation and human approval (tested shape)

The sandbox shared backend (21 LIVE-PROTOCOL tests) enforces, in order: bearer identity → surface owned by the caller's tenant (`404 SURFACE_NOT_FOUND` for another tenant's surface or a missing one) → role → strict context schema (`422`) → HITL. A sensitive `form.submit` never executes: it returns an `ApprovalRequest` surface whose text the server writes. `approval.approve` must come from an approver in the same tenant who is not the requester (`403 APPROVAL_SELF`), for a pending request id the server issued (`404` for forged or other-tenant ids), and only once (`409` on replay). Removing the HITL branch or the idempotency store made their tests fail.

## Authorization comes from the server, never the model

```python
def _lookup(self, principal: Principal, kind: str, resource_id: str) -> Resource | PendingOperation:
    ...
    resource = self.resources.get((kind, resource_id))
    if resource is None or resource.tenant != principal.tenant:  # cross-tenant looks like "absent"
        raise ActionRejected(404, "NOT_FOUND", f"no such {kind}")
    if resource.owner != principal.subject:
        raise ActionRejected(403, "FORBIDDEN", f"{kind} belongs to another user")
    return resource
```

- `principal` comes only from the verified token. A `userId`, `role` or `tenantId` in `context` is rejected by the payload schema; even if the schema allowed one, the code never reads it.
- An id from another tenant returns 404, the same as an id that does not exist, so the response does not reveal that the resource exists. A resource in the same tenant that belongs to another user returns 403.
- The model may *suggest* an id (it wrote `itemId` into the surface). The server *decides* whether this user may act on it. Prompt injection can change what the surface offers. It cannot change this check.
- A model never sees, generates or calls an authorization decision. Authorization is not a tool the agent can call.

## Rendered-by-us binding

The server records every `updateComponents` it streamed to a user, in a bounded per-user registry, and removes the entries on `deleteSurface`. An action is accepted only if a component this server rendered for this user declares that action name:

```python
if not self.registry_for(principal).declares(action["surfaceId"], action["sourceComponentId"], name):
    raise ActionRejected(409, "NOT_RENDERED", "no component this server rendered for you declares this action")
```

This blocks actions the user was never offered, such as a hand-crafted `approval.approve` against a surface that only showed an ActionCard. It also blocks actions replayed against another user's surface. In a multi-instance deployment, keep the registry in shared storage (for example Redis) keyed by user and surface. The reference keeps it in memory.

## Idempotency

The catalog marks side-effecting actions `requiresIdempotencyKey: true`. The client generates one key per user intent and sends it in the `Idempotency-Key` header. It is never put in `context`, because the client message allows exactly two properties (`version` and `action`; verified for v0.9, and the 1.0 action example in the a2ui.org agent-integration guide has the same shape).

```python
scope = (principal.subject, key)
lock = self._locks.setdefault(scope, asyncio.Lock())
async with lock:  # a concurrent duplicate waits, then replays the stored result
    stored = self._idem.get(scope)
    fp = fingerprint(action)          # sha256 of name+surfaceId+sourceComponentId+context (not timestamp)
    if stored is not None:
        if stored[0] != fp:
            raise ActionRejected(409, "IDEMPOTENCY_KEY_REUSED", "this key was used for a different action")
        return ActionOutcome(stored[1].status_code, stored[1].body, replayed=True)
    outcome = self._authorize_and_execute(...)
    self._idem[scope] = (fp, outcome)  # bounded LRU (idempotency_capacity)
```

- Keys are scoped per principal, so one user's key never collides with another's.
- Replays return the stored body with `Idempotent-Replayed: true`. The test shows 5 concurrent identical requests produce exactly 1 side effect.
- The timestamp is excluded from the fingerprint because a client retry may stamp the same intent again.
- Production: store keys durably with a TTL (24 h is common) in the same transaction as the side effect, so that a crash between "execute" and "remember" cannot double-apply. The in-memory LRU in the reference is not crash-safe.

## Human approval for high-risk actions

`approval.approve` and `approval.reject` are `risk: high, requiresHumanApproval: true`. The server does not execute them when they arrive. It holds the operation under a new `dialogId` and returns 202 with A2UI messages for a `ConfirmationDialog` whose **text the server writes** from its own data:

```python
dialog_id = "dlg-" + secrets.token_hex(8)
self.pending[dialog_id] = PendingOperation(dialog_id, principal.subject, principal.tenant, name,
                                           (target.kind, target.resource_id), dict(context))
messages = confirmation_surface(self.contract.catalog_id, dialog_id, name, target.resource_id)
for msg in messages:
    self.contract.validate_server_message(msg)   # server-authored UI passes the same gate
    self.registry_for(principal).record(msg)     # so dialog.confirm is "rendered by us"
return ActionOutcome(202, {"status": "confirmation_required", "dialogId": dialog_id, "messages": messages})
```

`dialog.confirm` carries only `{dialogId}`. The server executes the operation it stored, never one named in the payload. It re-checks authorization when the operation runs, not only when it was held. After that the dialog is closed, so a second confirm returns 409 `DIALOG_CLOSED`. Another user cannot confirm the dialog, because it was never rendered to them. The model therefore cannot write the sentence a human approves, and cannot skip the click.

## Audit

Every decision appends one record: subject, tenant, action, surface, decision (`allowed` / `denied` / `replayed`) and code. The log is bounded in memory in the reference; production writes it to an append-only store. It never contains tokens, full `context` values or free text from the model.

## Safe URLs and content

- The catalog's `forbiddenStringPatterns` (`javascript:`, `vbscript:`, `data:text/html`, `<script`) are checked on every string in every server message before streaming (`UNSAFE_CONTENT`). Renderers still render text as text, never as HTML.
- Navigation actions such as `item.open` carry an **id**, never a URL. The host app maps the id to a route. A model-supplied URL is never opened.
- No HTML, JavaScript or Dart execution comes from model output. Catalog `functionCall` actions are rejected (`FUNCTION_ACTION_FORBIDDEN`).

## Checklist

- [ ] Identity comes only from the verified token; 401 carries `WWW-Authenticate`
- [ ] Allowlist and payload schema come from the shared catalog, not hand-copied
- [ ] Rendered-by-us binding is enforced, and the registry is bounded
- [ ] Tenant check returns 404 and owner check returns 403; tests prove both
- [ ] Idempotency is scoped per principal; duplicate and concurrent duplicate requests are tested; a reused key with a different action returns 409
- [ ] High-risk actions are held, confirmed through server-authored text, and re-authorised when they execute
- [ ] Values the model offered are re-validated against server data
- [ ] Every decision is audited without secrets or model text
- [ ] The AG-UI or any other inbound path calls the same `ActionService.handle` ([ag-ui-transport.md](ag-ui-transport.md))

Related: [security-reviewer](../../security-reviewer/SKILL.md) skill (web sinks, tokens, CSRF), [tool-execution-safety.md](../../agentic-ai-dev/reference/tool-execution-safety.md) (agent-side tool risk).
