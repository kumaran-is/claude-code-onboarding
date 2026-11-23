---
paths:
  - "**/a2ui/**"
  - "**/genui/**"
  - "**/*catalog*.json"
  - "**/a2ui*.ts"
  - "**/a2ui*.tsx"
  - "**/genui*.ts"
  - "**/a2ui*.dart"
  - "**/genui*.dart"
---

# Generative UI (A2UI) guardrails

Path-scoped: loads only for GenUI directories and files (never all `.ts` / `.dart`). Depth: contract and backend topology `.claude/skills/genui-contract/`; Angular [a2ui-angular](../skills/a2ui-angular/SKILL.md); React `.claude/skills/react-spa/reference/generative-ui-a2ui.md`; Flutter [flutter-genui](../skills/flutter-genui/SKILL.md); streaming [streaming-protocols](../skills/streaming-protocols/SKILL.md). Review: `genui-contract-reviewer` agent. Commands: `/scaffold-genui-feature`, `/audit-a2ui-parity`, `/validate-genui-feature`.

- **Contract first.** One framework-neutral catalog (component IDs, typed props, actions) with a JSON Schema and valid + invalid fixtures, validated before any renderer change. No framework class names on the wire; each platform maps IDs to its own components.
- **Explicit protocol version.** One wire version per stream, negotiated per client: A2UI **1.0** (`"version": "1.0"`, the target) when the client declares `a2uiRendererCapabilities` for a served 1.0 catalog, **v0.9.x** (`"v0.9"`/`"v0.9.1"`) when it declares only `a2uiClientCapabilities`, otherwise refuse the stream (HTTP: 406). A renderer declares 1.0 only after a test renders 1.0 fixtures with its real package. Never translate between versions without a documented, tested adapter; v0.8 is rejected. Catalog validation is not authorization. Exact SDK pins and per-renderer status: `genui-contract/reference/compatibility-matrix.md`. `post-edit-genui-advisory.sh` flags drift.
- **Model output is untrusted input.** SDK structural validation is not enough: `@a2ui/web_core` 0.16.1 and `@a2ui/agent` 0.2.1 `validatePayload` both accepted a non-allowlisted action, a `javascript:` URL and a v0.9 binding inside a 1.0 message. Strict schema validation on, plus the app contract gate (component and action allowlist, payload schema, URL scheme check) in front of the SDK and server-side authorization of every action; component and action allowlists; never render model output as HTML, JS or Dart (no `innerHTML`, `dangerouslySetInnerHTML`, `bypassSecurityTrust*`, `eval`, WebView of model content); URLs need a scheme + host allowlist.
- **Unknown or malformed components** render a safe placeholder or reject the surface, and log the error with context. Never crash, never drop silently. `@a2ui/angular` 0.16.0 without SDK validation only `console.error`s an unknown type and renders nothing: construct the `MessageProcessor` with `validationConfig: STRICT_VALIDATION` and an `errorHandler` (or keep an app allowlist in front of it) and show a user-visible fallback.
- **Server authorizes every action.** Authn/authz on the server for each action; never trust a model-supplied role, owner or tenant. Side-effecting actions carry an idempotency key; high-risk actions need explicit human confirmation.
- **Sensitive data:** no secrets in browser or mobile bundles; no PII or tokens echoed into the data model, prompts or logs.
- **Parity only where declared.** A platform the contract lists must map every catalog ID; an undeclared platform is not a gap.
- **Accessibility:** every generated control has name, role and state; focus is predictable when a surface appears; WCAG 2.2 AA (`.claude/skills/accessibility-audit/`).
- **Streaming:** per-event size limit, connect/idle timeouts, cancellation that stops rendering and server work, no replay of side-effecting actions on reconnect.
- **Testing:** contract tests via the validator + fixtures; web UI/E2E via Playwright; Flutter Android/iOS UI/E2E via Maestro only (`.claude/rules/testing-tool-selection.md`).
