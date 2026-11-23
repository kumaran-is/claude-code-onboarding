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
- **Explicit protocol version.** A2UI **v0.9** end to end (`"version": "v0.9"`), exact SDK pins (`@a2ui/angular@0.14.0` + `@a2ui/web_core@0.15.0` from `/v0_9`; `a2ui_flutter 0.4.0` + `a2ui_core 0.8.0`). Never mix v0.8 / v1.0 between agent, renderer and catalog; v1.0 is a documented future migration. `post-edit-genui-advisory.sh` flags drift.
- **Model output is untrusted input.** Strict schema validation on; component and action allowlists; never render model output as HTML, JS or Dart (no `innerHTML`, `dangerouslySetInnerHTML`, `bypassSecurityTrust*`, `eval`, WebView of model content); URLs need a scheme + host allowlist.
- **Unknown or malformed components** render a safe placeholder or reject the surface, and log the error with context. Never crash, never drop silently.
- **Server authorizes every action.** Authn/authz on the server for each action; never trust a model-supplied role, owner or tenant. Side-effecting actions carry an idempotency key; high-risk actions need explicit human confirmation.
- **Sensitive data:** no secrets in browser or mobile bundles; no PII or tokens echoed into the data model, prompts or logs.
- **Parity only where declared.** A platform the contract lists must map every catalog ID; an undeclared platform is not a gap.
- **Accessibility:** every generated control has name, role and state; focus is predictable when a surface appears; WCAG 2.2 AA (`.claude/skills/accessibility-audit/`).
- **Streaming:** per-event size limit, connect/idle timeouts, cancellation that stops rendering and server work, no replay of side-effecting actions on reconnect.
- **Testing:** contract tests via the validator + fixtures; web UI/E2E via Playwright; Flutter Android/iOS UI/E2E via Maestro only (`.claude/rules/testing-tool-selection.md`).
