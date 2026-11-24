# SAST Tool Configuration Reference

Configuration templates, CI/CD integration, and comparison matrix for all SAST tools used in the project stack.

## Tool Comparison Matrix

| Tool | Language | Install Command | Config File | CI Step | Strengths |
|------|----------|----------------|-------------|---------|-----------|
| **Semgrep** | All (30+ languages) | `pip install semgrep` | `.semgrep.yml` | `semgrep ci --config=auto` | Custom rules, fast, low false positives |
| **Bandit** | Python | `pip install bandit` | `.bandit` | `bandit -r . -f json` | Python-specific, mature, AST-based |
| **ESLint Security** | TypeScript/JavaScript | `npm i -D eslint-plugin-security` | `.eslintrc-security.json` | `eslint --plugin security src/` | Integrates with existing ESLint setup |
| **dart analyze** | Dart/Flutter | (built-in) | `analysis_options.yaml` | `dart analyze` | Official Dart tooling, zero setup |
| **SpotBugs** | Java | Maven plugin | `pom.xml` profile | `mvn verify -Pspotbugs` | Bytecode analysis, finds deep bugs |

## Semgrep Configuration

### `.semgrep.yml` Template

See `semgrep-custom-rules.md` for the full rule file. The template structure:

```yaml
rules:
  # Project-specific rules
  - id: rule-name
    pattern: <pattern>
    message: "Description and fix guidance."
    severity: ERROR|WARNING|INFO
    languages: [python, java, typescript]
    metadata:
      cwe: CWE-NNN
      owasp: ANN:YYYY
```

### GitHub Actions CI Step

```yaml
name: SAST Scan
on:
  pull_request:
    branches: [develop, main]

jobs:
  semgrep:
    runs-on: ubuntu-latest
    container:
      image: semgrep/semgrep:1.186.0  # native Semgrep; the semgrep-action wrapper is deprecated and archived
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: Run Semgrep
        run: semgrep scan --config .semgrep.yml --config p/security-audit --config p/owasp-top-ten --error
        # With a Semgrep AppSec Platform token, `semgrep ci` (env SEMGREP_APP_TOKEN) replaces the line above.
```

## Bandit Configuration

### `.bandit` Config

```yaml
exclude_dirs:
  - tests
  - venv
  - .venv
  - build
  - dist

# Include high-confidence, high-severity tests
tests:
  - B201  # flask_debug_true
  - B301  # pickle
  - B302  # marshal
  - B303  # md5/sha1
  - B304  # insecure cipher
  - B305  # insecure cipher mode
  - B307  # eval
  - B308  # mark_safe
  - B312  # telnetlib
  - B323  # unverified SSL
  - B324  # hashlib insecure
  - B501  # request_with_no_cert_validation
  - B502  # ssl_with_bad_version
  - B506  # yaml_load
  - B602  # subprocess_popen_with_shell_equals_true
  - B608  # hardcoded_sql_expressions

# Skip low-signal tests
skips:
  - B101  # assert_used (common in tests)
  - B404  # import_subprocess (too noisy)
```

### Run Command

```bash
# Full scan with JSON output
bandit -r src/ -f json -o bandit-report.json

# High severity only
bandit -r src/ -ll -ii -f json

# With config
bandit -r src/ -c .bandit -f json
```

## ESLint Security Configuration

### `.eslintrc-security.json`

```json
{
  "plugins": ["security"],
  "extends": ["plugin:security/recommended"],
  "rules": {
    "security/detect-object-injection": "error",
    "security/detect-non-literal-fs-filename": "error",
    "security/detect-eval-with-expression": "error",
    "security/detect-pseudo-random-prng": "error",
    "security/detect-buffer-noassert": "error",
    "security/detect-child-process": "warn",
    "security/detect-no-csrf-before-method-override": "error",
    "security/detect-non-literal-regexp": "warn",
    "security/detect-unsafe-regex": "error",
    "security/detect-possible-timing-attacks": "warn"
  }
}
```

### Run Command

```bash
# Scan with security config
eslint --config .eslintrc-security.json --ext .ts,.js src/

# JSON output for CI
eslint --config .eslintrc-security.json --ext .ts,.js --format json src/ > eslint-security.json
```

## dart analyze Configuration

### `analysis_options.yaml` (Security-Focused)

```yaml
analyzer:
  strong-mode:
    implicit-casts: false
    implicit-dynamic: false
  errors:
    missing_return: error
    must_be_immutable: error
    dead_code: warning

linter:
  rules:
    # Security rules
    - avoid_web_libraries_in_flutter
    - cancel_subscriptions
    - close_sinks
    - literal_only_boolean_expressions
    - no_adjacent_strings_in_list
    - throw_in_finally
    - unnecessary_statements
    - valid_regexps
    # Null safety
    - avoid_null_checks_in_equality_operators
    - no_logic_in_create_state
    - use_key_in_widget_constructors
```

### Run Command

```bash
dart analyze --fatal-infos --fatal-warnings
flutter analyze --fatal-infos --fatal-warnings
```

## False Positive Management

### 4 Suppression Patterns

| Tool | Suppression Syntax | Scope |
|------|-------------------|-------|
| **Semgrep** | `# nosemgrep: rule-id` (inline comment) | Single line |
| **Bandit** | `# nosec B602` (inline comment) | Single line |
| **ESLint** | `// eslint-disable-next-line security/rule-name` | Next line |
| **dart analyze** | `// ignore: rule_name` | Next line |

### Best Practices for Suppressions

- Every suppression MUST include a justification comment explaining why it is safe
- Suppressions must be reviewed in code review -- do not rubber-stamp them
- Track suppression count per rule; if a rule has >10 suppressions, evaluate whether the rule needs tuning
- Audit suppressions quarterly: search for `nosemgrep`, `nosec`, `eslint-disable`, `ignore:` across the codebase

## Risk Scoring

### Formula

```
risk_score = min(100, CRITICAL x 10 + HIGH x 7 + MEDIUM x 4 + LOW x 1)
```

### Severity Thresholds

| Score Range | Risk Level | Required Action |
|-------------|-----------|-----------------|
| 0-20 | Low | Review in next sprint |
| 21-50 | Medium | Fix before next release |
| 51-80 | High | Fix before merge |
| 81-100 | Critical | Block merge, fix immediately |

### Severity Mapping Across Tools

| Semgrep Severity | Bandit Severity | ESLint Level | Risk Weight |
|-----------------|----------------|--------------|-------------|
| ERROR | HIGH | error | CRITICAL (10) or HIGH (7) |
| WARNING | MEDIUM | warn | MEDIUM (4) |
| INFO | LOW | off | LOW (1) |

Map tool-specific severities to the unified risk score using the weights above. When a finding
from one tool maps ambiguously (e.g., Semgrep ERROR could be CRITICAL or HIGH), use the CWE
and context to determine: exploitation without authentication = CRITICAL, requires authenticated
access = HIGH.
