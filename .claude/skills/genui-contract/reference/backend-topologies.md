# Backend topologies: `shared-backend` vs `standalone-backend`

> **Pins and proven wire version per platform:** see [compatibility-matrix.md](compatibility-matrix.md) (source of truth). Serve each client only the version it declares and is proven on. Every renderer and backend needs a contract gate in front of `@a2ui/web_core` (action allowlist, URL schemes, one version per stream, reject legacy `{"path"}` bindings in 1.0 with `SCHEMA_INVALID`), because web_core 0.16.1 and `@a2ui/agent` 0.2.1 accept these.

Every platform renders the same canonical catalog ([canonical-catalog-v1_0.json](canonical-catalog-v1_0.json) for 1.0, [canonical-catalog.json](canonical-catalog.json) for v0.9.x). What changes between topologies is who owns the server that streams A2UI messages and receives actions. The catalog, fixtures and action rules stay the same in both. The wire version is negotiated per client: A2UI 1.0 when the client declares it, v0.9.x when the client declares only that ([ag-ui-transport.md](ag-ui-transport.md#version-and-catalog-negotiation-v10-preferred-v09x-fallback)). The same catalog exists once per wire version (same component ids and actions), because one catalog document targets exactly one protocol version.

Evidence: both topologies are built from one reference app (FastAPI 0.165.0, sse-starlette 3.7.1, ag-ui-protocol 1.0.0, Python 3.14), started with `--mode shared` or `--mode standalone --client angular|react|flutter`. That app has 60 pytest tests, all passing, and the same tests pass in both modes. **DOCUMENTED AND TESTED** for the behaviour described here. The diagrams are **RECOMMENDED PRACTICE**.

## When to choose which

| Question | `shared-backend` | `standalone-backend` |
|---|---|---|
| Who owns the agent? | One team runs one agent service for every client | Each client team runs its own BFF (backend for frontend) that calls the agent, or embeds one |
| Release coupling | Every client gets the new behaviour at the same time; catalog changes need all renderers ready first | Each BFF ships on its own schedule; the catalog version is pinned per BFF |
| Per-client logic | Kept small: capability negotiation only | Allowed in the BFF (layout choice, per-platform feature flags) |
| Ops cost | 1 deployment, 1 set of credentials, 1 audit trail | N deployments, and N places that must enforce the same rules |
| Choose when | One product with web and mobile clients, and one agent team | Clients belong to separate products or teams, or one client needs an extra server-side integration |

Default to `shared-backend`. Move to `standalone-backend` only when one of the reasons in the last row applies. Each standalone BFF must repeat every rule in [action-security.md](action-security.md). It is a copy of the server rules, not a lighter version of them.

## What is shared and what is not

| Shared in both topologies (a contract; a change goes through a catalog version bump) | Not shared |
|---|---|
| Catalog: component IDs, props, `x-genui` limits and forbidden patterns | Layout and widget code (Angular components, React components, Flutter widgets) |
| Action allowlist and every `payloadSchema` | Styling and theme beyond the catalog `theme` |
| Surface IDs and data-model shapes used in fixtures | Client state management (signals, TanStack Query, Riverpod) |
| Golden action payloads (`fixtures/actions/`) | Transport client library (EventSource, fetch, `package:http`) |
| Authorization expectations: who may act on which resource, and the 401/403/404/409 codes | Server framework (FastAPI, NestJS, Spring) when each BFF is separate |
| Contract tests: every server runs every fixture; every client replays the same fixtures | |

## Rules that hold in both

1. **Credentials never reach a client.** Model keys, agent service credentials and database credentials stay in the server process, loaded from the environment or a secret manager. Clients hold only the user's own session or bearer token.
2. **The server validates before it streams.** Each A2UI message passes `Contract.validate_server_message` (version, wire schema, catalog, forbidden patterns, depth). Each surface passes the graph check (root, dangling references, cycles) before the first byte leaves the server. See [backend-emitters.md](backend-emitters.md).
3. **The server authorises every action.** It uses the authenticated principal, never the action `context` ([action-security.md](action-security.md)).
4. **One wire version per stream, negotiated.** A stream carries the version the client declared (`"1.0"` preferred, else `"v0.9"`). A client that declares neither gets `406`, and a message in another version is rejected (`UNSUPPORTED_VERSION` / `MIXED_VERSIONS`), never parsed best-effort or translated.
5. **Catalog validation is not authorization.** A payload that passes the catalog can still carry an action the user may not perform ([action-security.md](action-security.md#catalog-validation-is-not-authorization)).

## `shared-backend` architecture

```mermaid
flowchart LR
    subgraph Clients
        NG[Angular SPA<br/>@a2ui/angular v0_9]
        RE[React SPA<br/>A2UI renderer]
        FL[Flutter app<br/>a2ui_flutter adapter]
    end
    subgraph Server["shared-backend (one deployment)"]
        API[HTTP edge<br/>bearer auth + CORS]
        STR[A2UI SSE stream<br/>/a2ui/stream]
        AGUI[AG-UI stream<br/>/agui optional]
        ACT[Action pipeline<br/>/actions]
        GATE[Contract gate<br/>catalog + v0.9 schemas]
        AGENT[Agent<br/>ADK or LangGraph]
    end
    CAT[(Canonical catalog<br/>+ fixtures)]
    DATA[(Domain data<br/>owner + tenant)]
    NG --> API
    RE --> API
    FL --> API
    API --> STR
    API --> AGUI
    API --> ACT
    AGENT --> GATE
    GATE --> STR
    GATE --> AGUI
    CAT --> GATE
    CAT --> ACT
    ACT --> DATA
```

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (any platform)
    participant S as shared-backend
    participant A as Agent
    C->>S: GET /a2ui/stream (Bearer)
    S->>S: authenticate, authorise scenario
    S->>A: run
    A-->>S: candidate A2UI message
    S->>S: validate + fold surface state
    S-->>C: SSE data {version v0.9, createSurface}
    S-->>C: SSE data {updateComponents}
    S-->>C: event done
    C->>S: POST /actions {version v0.9, action} + Idempotency-Key
    S->>S: allowlist, rendered-by-us, payload schema, authz
    alt high-risk action
        S-->>C: 202 confirmation_required + ConfirmationDialog messages
        C->>S: POST /actions dialog.confirm
    end
    S-->>C: 200 result (replayed on duplicate key)
```

## `standalone-backend` architecture

```mermaid
flowchart LR
    NG[Angular SPA] --> BA[Angular BFF<br/>standalone-backend]
    RE[React SPA] --> BR[React BFF<br/>standalone-backend]
    FL[Flutter app] --> BF[Flutter BFF<br/>standalone-backend]
    CAT[(Canonical catalog<br/>+ fixtures<br/>pinned version)]
    CAT --> BA
    CAT --> BR
    CAT --> BF
    BA --> AG[Agent service<br/>internal credential]
    BR --> AG
    BF --> AG
    BA --> DATA[(Domain data)]
    BR --> DATA
    BF --> DATA
```

```mermaid
sequenceDiagram
    autonumber
    participant C as Flutter app
    participant B as Flutter BFF
    participant A as Agent service
    C->>B: POST /a2ui/stream (user Bearer)
    B->>B: authenticate user, derive identity server-side
    B->>A: run (internal credential, request id)
    A-->>B: A2UI messages
    B->>B: validate against the SAME pinned catalog
    B-->>C: SSE A2UI v0.9 (one message per event)
    C->>B: POST /actions + Idempotency-Key
    B->>B: same pipeline as shared-backend
    B-->>C: result
```

A BFF passes frames through as bytes once they are validated. If the upstream connection, a read or a status check fails, the BFF sends one terminal `error` frame. This follows rule 11 in [server-stream-lifecycle.md](../../streaming-protocols/reference/server-stream-lifecycle.md).

## Independent backends: share the contract, not the code

`standalone-backend` does not mean "copy the shared backend". Two teams may build their servers in different stacks and with different libraries. What they must share is the published catalog (per wire version), the action allowlist and the contract tests, never source code.

Evidence (**DOCUMENTED AND TESTED**, Node 26 sandbox): a shared backend and two independent backends were run against the same contract test. Team A used `@a2ui/agent` 0.2.1 for validation and `@ag-ui/encoder` 1.0.5 for framing; team B used neither and wrote AG-UI SSE frames and A2UI messages by hand. The test parsed every stream with `@ag-ui/client` 1.0.5 `HttpAgent`, validated each surface with `validatePayload` against both catalogs (1.0 and v0.9), and compared the component and action structure across all three: 10 contract tests passed. Planting a wrong wire version (`"v1.0"` instead of `"1.0"`) or an unknown component in team B made the contract test fail.

| Must match across independent backends | May differ |
|---|---|
| Catalog ids per version, component ids, action names and context schemas | Language, framework, SDK or none |
| Negotiation outcome for the same declared capabilities, and the 401/403/404/406 codes | Logging, persistence, deployment |
| AG-UI envelope: `ACTIVITY_SNAPSHOT`, `activityType: "a2ui-surface"`, `content.a2ui_operations`, `replace: true` | Internal agent logic |

## Running both topologies locally

```bash
export GENUI_DEMO_TOKEN_USER_A=<random-16+>   # from your shell, never committed
export GENUI_DEMO_TOKEN_USER_B=<random-16+>
uv run python -m genui_backend --mode shared                      # :8710, CORS for :4200 and :5173
uv run python -m genui_backend --mode standalone --client angular # :8711, CORS for :4200 only
uv run python -m genui_backend --mode standalone --client flutter # :8713, no CORS (native client)
```

`--mode standalone` without `--client` exits with code 2. Every response carries `X-GenUI-Topology` (`shared-backend` or `standalone-backend; client=<name>`), so a parity test can confirm which server it reached. A missing demo-token variable stops startup (fail closed). A fixture that fails the contract also stops startup.

## Contract tests every topology runs

| Test | Expectation |
|---|---|
| Every `fixtures/valid/*.json` | Streams unchanged and ends with `done` |
| Every `fixtures/invalid/*.json` | Rejected with its `expectedError` code (all 20 match in the reference app) |
| Every golden `fixtures/actions/*.json` | Accepted after its fixture surface is rendered to the same user |
| Wrong version, unknown action, other user's resource, other tenant's resource, duplicate key, cancel, reconnect | 400 / 400 / 403 / 404 / replay / generation stops / resume or re-sync |
