---
paths:
  - "**/*.dart"
  - "**/pubspec.yaml"
  - "**/AndroidManifest.xml"
  - "**/Info.plist"
---

# Flutter engineering guardrails

Path-scoped: loads only when Flutter/Dart files are in play. These are the always-apply guardrails; each links to the reference holding the reasoning, snippets and checklists (`.claude/skills/flutter-mobile/reference/`). Architecture-specific items apply only **if the project uses** that technology.

- **Never clear credentials, queues or caches on a transient failure.** Wipe only on an explicit credential rejection (e.g. refresh token refused), never on a connection error or timeout. → `flutter-security-hardening.md`, `flutter-offline-cache-and-reads.md`
- **Offline writes:** mint the idempotency key once at enqueue, persist it, reuse it on every retry; commit the local change and the queue entry in one transaction; retry only retryable failures within a bounded window. → `flutter-offline-reliability.md`
- **Offline is not a domain error.** Map transport failures, timeouts and server rejections to distinct states; show "offline" as offline, never as "invalid input". → `flutter-api-contract-parity.md`, `global-error-handling.md`
- **No service secrets in the app binary.** The client holds a user token and talks to a backend that holds the secrets. → `flutter-security-client-trust.md`
- **Async lifecycle:** guard every write after an `await` with a mounted/disposed check; a "never throws" contract must catch `Object`, not only `Exception`. If the project uses Riverpod 3, use `ref.mounted`, `.value` (not `valueOrNull`), and `container.listen` (not `read`) outside the widget tree. → `riverpod-patterns` skill
- **Navigation:** a redirect must wait for auth to resolve before deciding; a sheet or dialog that closes by navigating needs an explicit pop-safety check. → `flutter-navigation-and-auth-boot.md`
- **UI code does not call the network layer directly** when the project has a repository/use-case layer; mark intentional online-only code with `// online-only: <reason>`. A hook reports violations as advice.
- **Design tokens, not literals,** for colors, spacing, radii, durations and text styles; an `// ignore-design: <reason>` marker counts only on the same line or the line above. Use `.withValues(alpha:)`, not the deprecated `.withOpacity(`. → `flutter-design-polish.md`, `ui-standards-tokens` skill
- **User-visible strings are localized**, including semantics labels and tooltips; plural and gender forms use ICU messages. → `flutter-localization.md`
- **Pin external dependencies exactly** (no caret/`any`/`latest`; workspace members use a constraint their local version satisfies), verified on pub.dev; a discontinued package is replaced, not pinned. → `package-evaluation.md`
- **Never weaken a test to get green.** Fix the cause. → `flutter-testing-traps.md`
