# Flutter Mobile References

## Quick Navigation

| Reference | When to Load | Key Content |
|-----------|-------------|-------------|
| [mfri-scoring.md](mfri-scoring.md) | **Before any UI code** — Iron Law | MFRI risk score checkpoint; score < 3 = stop |
| [flutter-templates.md](flutter-templates.md) | Creating any new file | pubspec.yaml, Freezed models, Riverpod providers, screens, GoRouter, tests, Firebase patterns |
| [flutter-architecture-patterns.md](flutter-architecture-patterns.md) | Designing feature structure or state logic | Sealed classes, Result types, Riverpod AsyncNotifier, clean arch layers |
| [flutter-performance-ux.md](flutter-performance-ux.md) | Optimizing, adding animations, or improving UX | Accessibility, performance, haptic feedback, shimmer, animation patterns |
| [dart-language-pitfalls.md](dart-language-pitfalls.md) | Writing or reviewing Dart code | `late` overuse, ignored Futures, records, `final`, unchecked `as`, interpolation, collection literals, splitting large state classes, reading analyzer output honestly |
| [global-error-handling.md](global-error-handling.md) | Setting up app bootstrap, crash reporting, or error-to-state mapping | The 4 error entry points, fallback widget, integration checklist, error taxonomy (never map one failure class onto another) |
| [package-evaluation.md](package-evaluation.md) | **Before adding any pub.dev dependency** | pub.dev quality signals, license compatibility, pre-add checklist, red flags, version pinning, multi-package governance |
| [firestore-status-bus.md](firestore-status-bus.md) | Consuming backend-owned Firestore documents in real time (only if the project uses Firestore) | Read-only stream consumer pattern; the backend owns writes |
| [flutter-design-polish.md](flutter-design-polish.md) | Adding premium visual styling | Glassmorphism, premium cards, dark/light themes, gradients |
| [flutter-security-hardening.md](flutter-security-hardening.md) | Auth, secure storage, or data protection work (used by `flutter-security-expert`) | Certificate pinning, secure storage, privacy compliance |
| [accessibility-audit-checklist.md](accessibility-audit-checklist.md) | Adding interactive elements or running accessibility review (used by `accessibility-auditor`) | WCAG 2.1 AA checklist, Semantics widgets, touch targets |
| [flutter-network-resilience.md](flutter-network-resilience.md) | Any service/repository making HTTP or Firebase calls | Circuit breaker, retry with exponential backoff, timeout budgets, Riverpod integration |
| [flutter-offline-sync.md](flutter-offline-sync.md) | App must work without internet (create/edit/delete data offline) | Storage-neutral sync queue model and drain loop, tier model, conflict strategies, Riverpod integration |
| [flutter-testing-patterns.md](flutter-testing-patterns.md) | Writing tests for any feature (unit, widget, golden, integration) | mocktail fakes, ProviderContainer, ProviderScope overrides, golden tests |
| [flutter-offline-reliability.md](flutter-offline-reliability.md) | Building or reviewing the offline **write** path | Atomic enqueue, operation state machine, idempotency keys, failure classification and bounded retry, single-drainer lease, upload staging, 24-item review checklist |
| [flutter-offline-cache-and-reads.md](flutter-offline-cache-and-reads.md) | Building or reviewing the offline **read** path | Queued-write display, temp-id aliasing, non-destructive refresh, account-bound cache, migrations, backup exclusion |
| [flutter-navigation-and-auth-boot.md](flutter-navigation-and-auth-boot.md) | Router redirects, route gates, pre-`runApp` bootstrap, cold-start auth, deep links, Android Back | Redirect semantics, auth-resolution ordering, sheet/dialog safety |
| [flutter-api-contract-parity.md](flutter-api-contract-parity.md) | API client, DTO, base URL, timeouts, failure mapping | Contract parity checks, network-vs-domain error separation, bounded termination |
| [flutter-testing-traps.md](flutter-testing-traps.md) | A green test you do not trust, flaky suites, red gates, choosing validations | Widget-test traps, vacuous-pass defenses, `fakeAsync`, golden determinism, outcome classification, validation matrix |
| [flutter-e2e-maestro.md](flutter-e2e-maestro.md) | Maestro flows, `integration_test` vs Maestro, device prep | Flow conventions, iOS/Android divergences, evidence, deep-link/push testing |
| [flutter-localization.md](flutter-localization.md) | UI copy, ARB keys, plurals, locale formats | gen-l10n setup, ICU plural/select, parity vs coverage, locale selection |
| [flutter-build-and-workspace.md](flutter-build-and-workspace.md) | Melos 7+ workspace, local-backend run targets, Gradle, signed URLs, isolates | Pub workspaces, host per run target, memory sizing, `Isolate.run` |
| [flutter-security-client-trust.md](flutter-security-client-trust.md) | What may ship in the app binary, debug gates, local DB encryption | Client-secret rules and gate, fail-closed settings, token lifecycle |
| [flutter-platform-gotchas.md](flutter-platform-gotchas.md) | Native iOS/Android configuration | UIScene, cleartext/local network, Gradle and manifest traps |
