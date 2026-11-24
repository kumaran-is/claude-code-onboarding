# Code Deduplication Analysis Methodology

Phases 1-4 below show the Flutter scan; the triage, test-first, never-delete and cross-stack sections apply to every stack.

## No Cleanup Without Tests

Run the stack's test suite before touching anything and record the pass count: that is the baseline. Where coverage of the code being cleaned is thin, write characterization tests first. They pin current behaviour, not intended behaviour:

```python
def test_process_order_current_behavior():
    # Documents what the code does today; a cleanup must not change it
    assert process_order({"id": "1", "items": []}) == {"status": "empty", "total": 0}
```

After cleanup the same suite and the build must pass with the same or a higher count. Code with no tests and no feasible characterization test goes under THINGS I DIDN'T TOUCH, not into the cleanup.

## Analysis Phases

### Phase 1: Project Discovery

```bash
# Understand project structure
flutter pub deps --style=compact
dart analyze --format=machine
```

Identify:
- Feature modules in `lib/features/`
- Shared utilities in `lib/shared/` and `lib/core/`
- Test coverage in `test/`

### Phase 2: Duplicate Pattern Detection

Scan for common Flutter duplication patterns:

| Pattern | Search Strategy |
|---------|-----------------|
| Color definitions | `Color(0x`, `Colors.`, `ColorScheme` outside theme |
| Text styles | Inline `TextStyle(` not from theme |
| Padding/spacing | Repeated `EdgeInsets.all(16)` patterns |
| API endpoints | Hardcoded URL strings |
| Validators | Email, phone, password validation logic |
| Date formatters | `DateFormat` instantiation patterns |
| Error handling | Repeated try-catch patterns |

### Phase 3: Dead Code Detection

Identify unused exports by cross-referencing:

```dart
// Find all public exports
Grep: ^(class|enum|mixin|extension|typedef)\s+\w+

// Trace imports to find orphans
Grep: import '.*<filename>'
```

Check for:
- Widgets never instantiated
- Providers never watched/read
- Repository methods never called
- Models without usage
- Unused route definitions

### Phase 4: Dependency Audit

Compare `pubspec.yaml` against actual imports:

```bash
# List all dependencies
grep -E "^\s+\w+:" pubspec.yaml

# Find actual imports
grep -rh "import 'package:" lib/ | sort -u
```

Flag:
- Dependencies with zero imports
- Dev dependencies used in lib/
- Transitive dependencies that could be direct

## Triage Matrix

| Debt type | Cleanup risk | Value | Priority |
|-----------|--------------|-------|----------|
| Duplicated logic that has diverged (different bugs) | Medium | High | P1 |
| Dead code (no callers) | Low | Medium | P1 |
| Unused dependency | Low | High | P1 |
| Identical duplicated logic (3+ copies: Rule of Three) | Low | Medium | P2 |
| Premature abstraction | Medium | Medium | P2 |
| Complex but working, poorly tested code | High | Low | P3 |

P1: fix in this cleanup. P2: this sprint. P3: log a backlog item; only with dedicated refactor time and tests. Ship cleanups as small, separately reviewable PRs.

## Cross-Stack Unused Code and Dependency Detection

Check-only commands (no auto-fix); every hit still needs the never-delete checks below.

| Stack | Unused code | Unused dependencies |
|-------|-------------|---------------------|
| Node / NestJS / Angular / React | `npx knip` (unused files, exports, dependencies) | `npx knip --dependencies` |
| Python | `uv run --no-sync ruff check --select F401,F811,F841 src/` (unused import, redefined-while-unused, unused variable) | `deptry .` (declared but unused, used but undeclared) |
| Java (Maven) | IDE inspections; compiler warnings | `./mvnw dependency:analyze` ("Unused declared dependencies found") |
| Flutter / Dart | `dart analyze` (unused imports, private elements, locals); Phase 3 grep for public symbols | Phase 4 grep of `pubspec.yaml` against `import 'package:` lines |

`depcheck` is no longer maintained and its README recommends `knip`; do not add it. `flutter pub outdated` reports newer versions only; it does not detect unused packages. Outdated packages with CVEs are security work (`/security-dependencies`), not dedup.

## Output Format

```markdown
## Dedup Analysis Report

### Critical (Remove immediately)
- **Unused dependency**: `package:unused_lib` (0 imports)
- **Dead widget**: `lib/features/old/legacy_widget.dart` (0 references)

### Warning (Review recommended)
- **Duplicate colors**: 5 files define `primaryBlue = Color(0xFF1976D2)`
  - `lib/features/auth/theme.dart:12`
  - `lib/features/home/styles.dart:8`
  - ...
- **Similar validators**: Email validation in 3 locations

### Suggestions (Low priority)
- **Consolidate**: 4 date formatters could use shared utility
- **Consider removing**: `package:rarely_used` (1 import, alternatives exist)

### Statistics
- Files scanned: 142
- Potential duplicates: 23
- Unused exports: 7
- Unused dependencies: 2
```

## Safety Guidelines

**Avoid false positives:**
- Respect barrel exports (`index.dart` re-exports)
- Account for code generation (`.g.dart`, `.freezed.dart`)
- Check for dynamic widget usage via `runtimeType`
- Verify Riverpod providers may be watched in generated code
- Consider platform-specific code (`_ios.dart`, `_android.dart`)

**Never delete until each is confirmed:**
- No dynamic invocation: reflection, late binding, DI by name, plugin or route registries, `runtimeType` switches
- No caller outside this repo: public API or package export, other services, scripts, scheduled jobs
- No conditional or generated build path that activates it (flavours, platform files, code generation)
- Commented-out code: delete it (git history keeps it); do not re-enable it

**Do not flag:**
- Framework-required exports (main.dart, app.dart)
- Test utilities only used in test/
- Platform channel interfaces
- Route guards and middleware
- Lifecycle hooks

## Integration

Run standalone (`/dedup-code-agent`) or alongside `/review-code`:

```
User: Scan for duplicate code and unused dependencies
Agent: [Executes 4-phase analysis and produces report]
```

Pairs well with:
- `code-reviewer` -- For quality context
- `architect` -- For structural concerns
- `security-reviewer` -- For security impact assessment
