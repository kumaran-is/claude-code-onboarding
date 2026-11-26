# MCP Security Reference (canonical)

The one place that says which Model Context Protocol (MCP) security controls the **specification requires** and which are **recommended practice**, with the severity a reviewer assigns when one is missing. Used by `security-reviewer` (servers, transport, auth, MCP client config) and `ai-security-reviewer` (what an agent may do with tools). Implementation code, tested: `mcp-builder/reference/security-core.md` (auth), `security-middleware-attacks.md` (tool execution, SSRF, approvals), `security-pii-compliance.md` (secrets, errors, audit, PII), `production-runtime-multi-tenant.md` (tenant context, quotas).

**Revision:** MCP specification **2026-07-28** (current as of 2026-11-23; `specification/versioning`). That revision removed protocol sessions (`Mcp-Session-Id`) and the `initialize` handshake, deprecated Dynamic Client Registration in favour of Client ID Metadata Documents, and deprecated protocol logging. The Security Best Practices page is published under `docs/2026-07-28/tutorials/security/`; the normative authorization pages link to it. Servers still on 2025-11-25 keep session-bound rules (§2, row S6).

## 1. Requirement levels

Level = the keyword in the cited page. "Practice" = not in the MCP specification; source given.

### Authorization (HTTP transports)

| Control | Level | Applies to | Source |
|---|---|---|---|
| Authorization at all | OPTIONAL; when supported over HTTP, SHOULD conform | server | Authorization §Protocol Requirements |
| stdio: no OAuth flow, credentials from the environment | SHOULD NOT follow the spec | stdio server | same |
| Serve OAuth Protected Resource Metadata (RFC 9728) | **MUST** | server | Authorization §Overview 4 |
| Advertise it: `resource_metadata` in the 401 `WWW-Authenticate`, or the well-known URI | **MUST** (one of) | server | Authorization Server Discovery |
| `scope` in the 401 challenge | SHOULD | server | Authorization §Scope Selection Strategy |
| Validate access tokens (OAuth 2.1 §5.2) | **MUST** | server | Authorization §Token Handling |
| Token audience is this server (RFC 8707); accept only own tokens; do not accept or transit other tokens | **MUST / MUST NOT** | server | §Token Handling; Security Considerations §Access Token Privilege Restriction |
| Pass the received token to an upstream API (token passthrough) | **MUST NOT** | server | Security Considerations; Best Practices §Token Passthrough |
| Invalid or expired token → 401 | **MUST** | server | §Token Handling, §Error Handling |
| Insufficient scope → 403 + `error="insufficient_scope"`, `scope`, `resource_metadata` | SHOULD | server | §Scope Challenge Handling |
| Account for scope hierarchies when deciding sufficiency | **MUST** | server | §Step-Up Authorization Flow |
| Secure token storage (no tokens in logs or caches) | **MUST** | client and server | Security Considerations §Token Theft |
| Proxy with a static client ID: user consent per dynamically registered client | **MUST** | proxy server | Security Considerations §Confused Deputy |
| Bearer header on every request; never in the query string | **MUST / MUST NOT** | client | §Token Requirements |
| `resource` parameter in authorization and token requests | **MUST** | client | §Resource Parameter Implementation |
| PKCE `S256`; refuse an AS without `code_challenge_methods_supported` | **MUST** | client | Security Considerations §Authorization Code Protection |
| Validate `iss` in the authorization response (RFC 9207) | **MUST** | client | §Authorization Response Validation |
| AS endpoints over HTTPS; redirect URIs localhost or HTTPS; exact redirect match | **MUST** | AS, client | §Communication Security, §Open Redirection |
| Client ID Metadata Documents | SHOULD (DCR deprecated) | AS, client | §Overview 2–3; `deprecated` registry |

### Transport and tools

| Control | Level | Source |
|---|---|---|
| Validate `Origin` on every Streamable HTTP request; present and invalid → 403 | **MUST** | Streamable HTTP §Security & Endpoint |
| Local servers bind 127.0.0.1, not 0.0.0.0 | SHOULD | same |
| Authenticate all connections | SHOULD | same |
| Clients treat tool annotations as untrusted unless the server is trusted | **MUST** | Tools §Tool |
| Human in the loop able to deny tool invocations; confirmation for sensitive operations | SHOULD | Tools (trust & safety) |
| Clients validate structured results against `outputSchema` | SHOULD | Tools §Output Schema |
| Handles: verify every request; possession of a handle is not authentication | **MUST / MUST NOT** | Best Practices §State Handle Hijacking |
| Handles random, expiring, bound server-side to the verified user | SHOULD | same |
| Clients that fetch URLs server-side: consider SSRF; block private/reserved ranges; validate redirect targets; egress proxy | MUST consider / SHOULD | Best Practices §SSRF |
| One-click local server install: consent before executing commands | **MUST** | Best Practices §Local MCP Server Compromise |
| Form-mode elicitation never requests passwords, API keys, tokens or payment credentials (use URL mode) | **MUST NOT** | Elicitation |

### Practice (not in the MCP specification)

| Control | Source |
|---|---|
| JWT access tokens: asymmetric `alg` allowlist; never `none`; key from the issuer's JWKS only | RFC 8725 §3.1–3.2 |
| Check `typ: at+jwt` (rejects ID tokens used as access tokens) | RFC 9068 §4 (MUST for resource servers using that profile) |
| `iss` exact, `exp` required, small clock skew; JWKS refetch on unknown `kid` with a cooldown | OAuth 2.1 §5.2; jose |
| Tenant and subject only from the verified token; strict input schemas; foreign = missing | OWASP API1:2023 (BOLA) |
| Per-tool scopes and a per-principal tool allowlist enforced at call time | least privilege |
| Server-verified human approval bound to principal + tool + arguments, single use, for destructive tools | this workspace (tested) |
| SSRF: library IP classification, resolve-then-pin, per-hop redirect validation, size/time caps | Best Practices §SSRF (pinning is "consider") |
| Rate limits and quotas per principal and per tenant in a shared store | OWASP API4:2023 |
| Retries only for idempotent calls; idempotency keys on writes; circuit breakers | this workspace |
| Audit before effect; redacted structured logs on stderr | this workspace |
| Fail closed: missing config, missing principal, unreachable policy store → refuse | this workspace |

## 2. Reviewer severity — MCP servers (`security-reviewer`)

| # | Finding | Severity |
|---|---|---|
| S1 | Remote HTTP server with tools on user or tenant data and no authentication, or auth that can be disabled by config in production without refusing to start | CRITICAL |
| S2 | Access token accepted without audience validation, or forwarded to an upstream API (passthrough) | CRITICAL |
| S3 | Tenant, user or account id taken from tool arguments, headers set by the client, or model text | CRITICAL |
| S4 | URL-fetching tool without an SSRF guard, or a string-prefix guard, or redirects followed without re-validation | HIGH (CRITICAL on a cloud workload with a metadata endpoint) |
| S5 | JWT verified without an `algorithms` allowlist, `iss` check or `exp`; HS* with a shared secret for a remote AS | HIGH |
| S6 | No Origin validation on Streamable HTTP; local server bound to 0.0.0.0; remote bind without `allowedHosts`/`allowedOrigins`; (2025-11-25 servers) session id not bound to the authenticating identity | HIGH |
| S7 | No Protected Resource Metadata or no `resource_metadata` in the 401 challenge on an OAuth-protected server | HIGH (spec MUST; clients cannot discover the AS) |
| S8 | Endpoint-wide scope only; any authenticated principal can call every tool | HIGH for write/destructive tools, MEDIUM for reads |
| S9 | Secrets in argv, in tool arguments or results, in logs; `error.message` from upstreams returned to the client | HIGH |
| S10 | Invalid token answered with 403 or 200; insufficient scope answered with 401 | MEDIUM |
| S11 | Unpinned or deprecated MCP SDK/adapter version on a security path | MEDIUM |
| S12 | No audit record for authorization denials, or a read tool returning PII/financial data/documents without one | MEDIUM (HIGH for payments/deletes) |
| S13 | Secret or credential requested through form-mode elicitation | HIGH (spec MUST NOT) |
| S14 | Write tool with no audit-log call, or the effect runs when the audit write fails | CRITICAL (eval-standard hard blocker: merge blocked) |
| S15 | Tool accepts a cross-scope input id, or an unauthorized tool call succeeds, in any test or canary | CRITICAL (eval-standard hard blocker) |
| S16 | No committed tool-surface lock (name + description + input schema hashes) checked in CI | MEDIUM |

Attack classes: tool-description or tool-output poisoning and excessive agency are AC-08, unsafe tool calls (forbidden transition, wrong recipient, mass action) AC-09; third-party tool-server intake (provenance, pin, surface review, egress, sandboxed identity with short-lived audience-restricted tokens, re-review on surface change, remote non-enterprise servers default to T2): `ai-threat-model-attack-classes.md` §3, §9.

## 3. Reviewer severity — tool execution (`ai-security-reviewer`)

| # | Finding | Severity |
|---|---|---|
| T1 | Authorization delegated to the model (prompt says "only for admins") | CRITICAL |
| T2 | Destructive or external-effect tool (delete, send, pay, publish) with no server-verified approval; `destructiveHint` treated as the control | CRITICAL |
| T3 | Tool output or resource content used as authority (recipient, URL, amount, id for a side effect) without allowlist/verified state | HIGH |
| T4 | Generic tools (`run_sql`, `http_request`, `exec`) where narrow intent tools would do | HIGH |
| T5 | Non-idempotent write retried, or no idempotency key | HIGH |
| T6 | No per-principal rate limit/quota on expensive or fan-out tools | MEDIUM |
| T7 | Regex injection detector used as a blocking control instead of a signal | MEDIUM |
| T8 | No `outputSchema` / result validation for tools whose output drives code | MEDIUM |
| T9 | Idempotency key not bound to a payload hash: a reused key with changed amount, recipient or date executes again or silently returns the old result | HIGH |
| T10 | Agent-retried write with no version / `supersedes` check, so a late AI write lands after a human resolved the object | HIGH (financial, scheduling, authorization effects), MEDIUM otherwise |
| T11 | Tool input without a strict schema (unknown fields stripped or accepted) or without a supported-version check | MEDIUM (HIGH when an extra field can carry scope, tenant or amount) |
| T12 | An agent caller's delegated permissions not intersected with the delegator's, or no maximum delegation depth | HIGH |
| T13 | Tool failure path returns fabricated data (empty list, `0`, default) instead of a typed error | HIGH |

## 4. MCP client configuration (`.mcp.json`, settings)

Complements [claude-config-security.md](claude-config-security.md) §4 (MCP launch lines, pins) and §1 (wildcard `mcp__*` permission grants).

| Finding | Severity | Fix |
|---|---|---|
| Secret expanded into `args` (`--api-key=${VAR}`, connection string with password) | HIGH | pass via `env` or the server's documented env variable; argv is visible to any process that lists processes |
| Server package deprecated or archived upstream | HIGH | move to the maintained replacement (often the vendor's hosted HTTP server with OAuth) |
| Static bearer secret in `headers` where the server supports OAuth | MEDIUM | drop the header and use OAuth (Claude Code reports "OAuth fallback is disabled when headers.Authorization is set" on a rejected header) |
| `npx -y pkg`, `pkg@latest`, `uvx --refresh` | MEDIUM | pin an exact version |
| Write-capable server with `--tools=all` or a wildcard permission | MEDIUM | enable only the tools the workflow needs; restricted keys |

## 5. Evidence a reviewer requires

- A runtime claim (401, 403, SSRF blocked, approval refused) counts only with the command and its output from this session; otherwise mark it **NOT RUN**.
- A guard test counts only with a **negative control**: the same test fails when the guard is removed. Tests against a mock that never calls the guard prove nothing.
- Static review cites `file:line` for the guard and for every call path that must pass through it (all fetch sites, all tools).
- A tool counts as release-ready only with evidence for all five tool-eval layers (protocol contract, schema, authorization + isolation, security, trajectory) and at least 5 cases per tool: `eval-guide/reference/mcp-eval-patterns.md`. A missing layer is NOT RUN, never PASS. Authorization and isolation verdicts come from deterministic tests, never from an LLM judge.

## 6. Sources (fetched 2026-11-23)

- Authorization: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization (and `/authorization-server-discovery`, `/security-considerations`)
- Streamable HTTP: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- Tools: https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- Security Best Practices: https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices
- Deprecated features: https://modelcontextprotocol.io/specification/2026-07-28/deprecated
- TypeScript SDK v2 authorization: https://ts.sdk.modelcontextprotocol.io/v2/serving/authorization
- RFC 9728, RFC 8707, RFC 9068, RFC 8725, RFC 9207, OAuth 2.1 (draft-ietf-oauth-v2-1-13)

## 7. MCP servers reviewed for this toolkit (risk register)

The single source of truth for WHICH servers are approved is `.claude/mcp-allowlist.txt` with `.claude/mcp-config.sha256`; `session-mcp-governance.sh` warns at session start when `.mcp.json` drifts from them. This register records WHY each one was approved and its risk. Every `.mcp.json` server has exactly one row here (checked both ways by `.claude/scripts/check-mcp-register.sh`). A new server passes the scan-before-trust check (`.claude/rules/skill-triggers.md` §P0) before it gets a row, an allowlist entry and a refreshed hash.

| MCP Server | Status | Risk Notes |
|------------|--------|------------|
| `github` (api.githubcopilot.com) | ✅ Trusted | HTTP MCP, reads/writes GitHub only |
| `angular-cli` (npx @angular/cli mcp) | ✅ Trusted | Local CLI, no network write calls |
| `chrome-devtools` (chrome-devtools-mcp) | ✅ Trusted | Local browser automation |
| `spartan-ui` (npx @spartan-ng/mcp@1.10.1) | ✅ Trusted | Official spartan/ui docs server (stdio, no key). Package scanned 2026-11-24: no process spawn or eval; network only to www.spartan.ng; writes only its cache (`~/.cache/spartan-mcp`) |
| `firebase` (npx firebase-tools mcp) | ✅ Trusted | Scoped to authenticated Firebase project |
| `context7` (npx @upstash/context7-mcp) | ✅ Trusted | Read-only doc fetcher |
| `dart-mcp-server` (dart mcp-server) | ✅ Trusted | Local Dart/Flutter tooling |
| `langchain-docs` (docs.langchain.com/mcp) | ✅ Trusted | Read-only doc fetcher — if your project standardizes on Google ADK, prefer `adk-docs` MCP instead |
| `postgres` (npx @modelcontextprotocol/server-postgres) | ⚠️ Archived | Package archived upstream (no security fixes); connection string in argv. Replace with a maintained server |
| `docker` (npx docker-mcp) | ⚠️ Elevated | Can manage containers — confirm scope per use |
| `xcodebuild` (xcodebuildmcp) | ✅ Trusted | Local Xcode build tooling |
| `maestro` (maestro mcp) | ✅ Trusted | Local mobile test runner |
| `adk-docs` (uvx mcpdoc) | ✅ Trusted | Read-only doc fetcher |
| `voicemode` (uvx voice-mode) | ⚠️ Elevated | Uses OpenAI STT/TTS — sends audio to external API |
| `weaviate-docs` (mcp-remote) | ✅ Trusted | Read-only doc fetcher |
| `stripe` (`.mcp.json`: npx @stripe/mcp) | ⚠️ Deprecated | Local package deprecated by Stripe (no security fixes); hosted mcp.stripe.com (OAuth) is the supported server. Key must come from `env`, not `--api-key` |
| `stitch` (stitch.googleapis.com/mcp) | ⚠️ Elevated | Official Google Stitch HTTP MCP. API key via `X-Goog-Api-Key: ${STITCH_API_KEY}` (never a literal). Can create/edit designs in the Stitch account that key belongs to. Setup: https://stitch.google.com/docs/mcp/setup |
| `revenuecat` (mcp.revenuecat.ai) | ✅ Trusted | Official RevenueCat HTTP MCP, OAuth-authenticated, subscription management |
| `gcp-*`, `firestore`, `cloud-sql-*`, `cloud-storage` (*.googleapis.com/mcp) | ⚠️ Elevated | Google-managed HTTP MCP servers; act with your Google Cloud credentials on any project they reach. Use a non-production project; `cloud-sql-postgres` is the read-only endpoint |
| `firebase-emulator` (npx firebase-tools@15.37.0 mcp) | ✅ Trusted | Same package as `firebase`, pointed at local emulators (127.0.0.1); use a `demo-*` project id |
| `weaviate-local` (localhost:8091) | ✅ Trusted | Local Weaviate instance only |
| `terraform` (docker hashicorp/terraform-mcp-server:1.4.1) | ✅ Trusted | Official HashiCorp image, pinned; registry docs lookup |
| `mobile-mcp` (npx @mobilenext/mobile-mcp@1.0.19) | ⚠️ Elevated | Drives local emulators/simulators. Exploratory only: Flutter UI/E2E tests stay Maestro-only |
| `appstore-connect` (npx @mgcrea/mcp-appstore-connect@0.32.2) | ⚠️ Elevated | Community package; key read from a `.p8` file path; writes disabled by default (`APP_STORE_CONNECT_ALLOW_WRITES=0`) |
| `google-play-developer` (npx google-play-developer-mcp@0.2.0) | ⚠️ Elevated | Community package; service-account credential; grant least Play Console permissions |
