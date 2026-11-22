# Package Evaluation — Flutter 3.41.x / Dart 3.10.9

Use before adding any pub.dev dependency. Applies to: Flutter 3.41.x / Dart 3.10.9 / pub.dev (as of 2026).

---

## Section 1 — pub.dev quality signals

Before adding any pub.dev dependency, evaluate ALL of the following:

| Signal | Threshold | Where to check |
|--------|-----------|----------------|
| Pub points | ≥ 130 / 160 | pub.dev package page score badge |
| Likes | Context-dependent (>100 for utilities, >500 for UI) | pub.dev likes count |
| Popularity | > 70% for general-use packages | pub.dev popularity % |
| Verified publisher | Must have verified publisher badge | pub.dev publisher badge (e.g., dart.dev, google.dev) |
| Null safety | Must support null safety | Dart 3 null safety badge |
| Last publish | < 12 months for active packages (exception: stable packages with no churn) | pub.dev "Published" date |
| Platform support | Must include iOS + Android for mobile packages | Platform tags on pub.dev |
| License | MIT, Apache 2.0, or BSD only | pub.dev license tab |

---

## Section 2 — License compatibility

| License | Mobile app use | Commercial use | Requires attribution |
|---------|---------------|----------------|---------------------|
| MIT | ✅ | ✅ | In app credits or NOTICE file |
| Apache 2.0 | ✅ | ✅ | In NOTICE file |
| BSD 2/3-clause | ✅ | ✅ | In app credits or NOTICE file |
| GPL v2/v3 | ❌ | ❌ | Copyleft — infects your app |
| LGPL | ⚠️ | ⚠️ | Dynamic linking only — get legal review |
| Proprietary | ⚠️ | ⚠️ | Check terms before use |

**Rule:** NEVER add a GPL-licensed package to a closed-source Flutter app without explicit legal
approval. GPL copyleft applies to the entire binary — it is not safe to assume "library use" is
exempt for statically linked mobile apps.

---

## Section 3 — Pre-add checklist

```
Before adding any pub.dev package:
□ Pub points ≥ 130
□ Verified publisher (or explicitly justified in PR)
□ License = MIT / Apache 2.0 / BSD
□ Null safety supported
□ Last published within 12 months (or stable/no-churn exception documented)
□ Package solves a problem we cannot solve reasonably ourselves
□ Not a thin wrapper around standard library (implement directly instead)
□ Open issues checked for critical/blocking bugs in our use case
```

---

## Section 4 — Red flags

- Package with 0 verified publisher AND < 50 pub points — likely unmaintained or low quality
- Package that hasn't been published in > 2 years — check if officially deprecated
- Package that requires platform-specific permissions beyond what it actually needs
- Multiple packages doing the same thing in `pubspec.yaml` — pick one and standardize
- Forked packages (`*_fork`, `*_fixed`) without explanation — prefer waiting for upstream fix
- Package with < 10 pub points — almost certainly not production-ready

---

## Section 5 — Recommended evaluation workflow

```bash
# 1. Visit pub.dev/packages/<package_name>
#    Check: score, verified publisher, license, last publish date, platform tags

# 2. Read CHANGELOG for breaking changes in latest version

# 3. Check Issues tab for critical bugs affecting your use case

# 4. Add the package:
flutter pub add <package_name>

# 5. Check for known vulnerabilities:
flutter pub get
# pub prints "affected by advisory" lines for any dependency with a published
# security advisory (see dart.dev/tools/pub/security-advisories). Review each link;
# upgrade, or record a justified entry in `ignored_advisories` in the ROOT pubspec only.
```

Run `pub get`/`pub upgrade` output review after every add or upgrade. Pub's advisory feed is the
verified mechanism; a dedicated `audit` subcommand was not confirmed when this file was written, so
check `dart pub --help` on your SDK before scripting around one. Add your org's CI dependency
scanner on top for transitive coverage.

---

## Section 6 — Version pinning

Pin to an exact version in `pubspec.yaml`. Never use `any` or open-ended ranges in production.
Look up the current stable version on pub.dev when adding the package (do not copy numbers from docs):

```yaml
dependencies:
  # Correct — exact pin (go_router 18.1.4 was current stable when this was written; re-check)
  go_router: 18.1.4

  # Forbidden in production
  some_package: any
  other_package: ">=1.0.0"  # unbounded upper bound
```

Commit `pubspec.lock` for apps (and the workspace root lockfile in a monorepo). When upgrading, run
`flutter pub outdated`, then evaluate each upgrade with the pre-add checklist (Section 3).

---

## Section 7 — Governance in multi-package repos

| Rule | Detail |
|------|--------|
| Shared-only packages | HTTP client, local DB, key-value store, font loader, image-cache packages are declared only in the shared package that wraps them — not re-declared in each app pubspec |
| Declared = imported | Every dependency in a shared pubspec must be imported by that package; remove unused ones |
| One package per job | Two packages doing the same thing (two HTTP clients, two DB layers) — pick one and migrate |
| Overrides | `dependency_overrides` only in the workspace root pubspec, one per package, each with a comment (reason + removal condition). See [flutter-build-and-workspace.md](flutter-build-and-workspace.md) |
| Ambiguous exports | A new top-level symbol in a shared barrel can break an app outside your diff (`ambiguous_import`): grep the tree first and run `flutter analyze` on every app |
| Discontinued / unmaintained | pub.dev shows "discontinued" and any replacement; do not add one, and plan migration for existing uses |
| Plugin pairing | Federated plugins (`foo` + `foo_platform_interface`) must resolve to compatible versions; a patch bump of a platform interface can break the method-channel contract at runtime, so pin it at the root until the app plugin catches up |
| Placeholder tests | `expect(true, isTrue)` or tests named placeholder/dummy are not coverage; delete or write a real assertion |
