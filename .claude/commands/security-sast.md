---
description: Static Application Security Testing across the full stack. Runs Bandit (Python), Semgrep (multi-language), ESLint Security (TypeScript/Angular), dart analyze (Flutter), SpotBugs (Java). Generates SARIF report with risk score 0-100.
allowed-tools: Bash, Read, Glob, Grep
disable-model-invocation: true
---

# SAST Security Scan

Run static application security testing on the specified path.

## Scan Path

Scan `$ARGUMENTS` if provided, otherwise the current directory. Claude Code substitutes `$ARGUMENTS` textually; `${ARGUMENTS:-.}` is never substituted and always meant `.`.

```bash
SCAN_PATH="$ARGUMENTS"; [ -n "$SCAN_PATH" ] || SCAN_PATH="."
```

## Step 1: Language Detection

```bash
[ -f "$SCAN_PATH/pom.xml" ] && echo "Java/Spring detected"
[ -f "$SCAN_PATH/package.json" ] && echo "TypeScript/Node detected"
{ [ -f "$SCAN_PATH/pyproject.toml" ] || [ -f "$SCAN_PATH/requirements.txt" ]; } && echo "Python detected"
[ -f "$SCAN_PATH/pubspec.yaml" ] && echo "Dart/Flutter detected"
```

## Step 2: Run Language-Specific Scanners

Each scanner writes to a log and reports its OWN exit code; never pipe a scanner into `grep`/`head` before reading it. Status per scanner: PASS (ran, exit 0) / FAIL (findings) / BLOCKED (tool, profile or config missing; crash) / NOT RUN (not configured, with the reason). Semgrep exits 0 even with findings unless `--error` is passed (checked on semgrep 1.186.0 with a planted finding: exit 0 without, 1 with). Bandit exits 1 on findings (checked).

```bash
# Java — SpotBugs needs a `spotbugs` profile in pom.xml; without it: BLOCKED, not clean
mvn -q verify -Pspotbugs -DskipTests > /tmp/sast-spotbugs.log 2>&1; echo "SPOTBUGS EXIT:$?"
semgrep scan --config=p/java --metrics=off --error --json-output=/tmp/sast-semgrep-java.json "$SCAN_PATH"; echo "SEMGREP JAVA EXIT:$?"
# TypeScript (NestJS, Angular, React, Node) — the project's own ESLint config; if it does not load
# eslint-plugin-security, report that check NOT RUN (do not add CLI plugin flags: flat config ignores them)
(cd "$SCAN_PATH" && npx eslint . > /tmp/sast-eslint.log 2>&1); echo "ESLINT EXIT:$?"
semgrep scan --config=p/typescript --metrics=off --error --json-output=/tmp/sast-semgrep-ts.json "$SCAN_PATH"; echo "SEMGREP TS EXIT:$?"
# Python — bandit exits 1 on findings at or above -ll (medium)
bandit -r "$SCAN_PATH" -ll -f json -o /tmp/sast-bandit.json; echo "BANDIT EXIT:$?"
semgrep scan --config=p/python --metrics=off --error --json-output=/tmp/sast-semgrep-py.json "$SCAN_PATH"; echo "SEMGREP PY EXIT:$?"
# Dart / Flutter — analyzer findings (security rules come from the project's analysis_options.yaml)
(cd "$SCAN_PATH" && flutter analyze > /tmp/sast-analyze.log 2>&1); echo "ANALYZE EXIT:$?"
# Project rules, when .semgrep.yml exists
[ -f "$SCAN_PATH/.semgrep.yml" ] && { semgrep scan --config="$SCAN_PATH/.semgrep.yml" --metrics=off --error --json-output=/tmp/sast-semgrep-local.json "$SCAN_PATH"; echo "SEMGREP LOCAL EXIT:$?"; }
```
Run only the blocks for detected ecosystems. A missing scanner (`command -v semgrep bandit mvn` fails) is BLOCKED with "install X". Findings are read from the JSON/log files. Web-only XSS sinks: `/xss-scan`; dependency CVEs: `/security-dependencies`; the full audit with an approval Lock Document: `/audit-security`.

## Step 3: Risk Score Calculation

```
Risk Score = min(100, sum of:
  CRITICAL findings x 10
  HIGH findings x 7
  MEDIUM findings x 4
  LOW findings x 1
)
```

## Step 4: Output

```
SAST SCAN RESULTS
=================
Path: [scanned path]
Languages: [detected languages]
Risk Score: [0-100]

CRITICAL ([count]):
  - [file:line] [finding description] [CWE]

HIGH ([count]):
  - [file:line] [finding description] [CWE]

MEDIUM ([count]):
  - [file:line] [finding description] [CWE]

LOW ([count]):
  - [finding description]

NEXT STEPS:
  [ ] Fix all CRITICAL findings before merge
  [ ] Review HIGH findings — fix or document accepted risk
  [ ] Run /security-hardening for comprehensive remediation
```

Use instead when: `/audit-security` — the full audit with a score and the Lock Document; `/xss-scan` — web XSS sinks with secure alternatives.

$ARGUMENTS
