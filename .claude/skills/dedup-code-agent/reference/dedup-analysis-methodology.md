# Code Deduplication Analysis Methodology

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
