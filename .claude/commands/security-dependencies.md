---
description: Multi-ecosystem dependency vulnerability scanner with SBOM generation and risk-weighted prioritization. Scans npm (NestJS/Angular), pip (Python), Maven (Java), pub.dev (Flutter). Outputs CycloneDX SBOM and prioritized CVE list.
allowed-tools: Bash, Read, Glob, Grep
disable-model-invocation: true
---

# Dependency Vulnerability Scanner

Scan project dependencies across multiple ecosystems to identify vulnerabilities, generate an SBOM, and provide risk-weighted prioritization.

## Arguments

$ARGUMENTS

## Instructions

### Step 1: Determine scan path and detect ecosystems

```bash
SCAN_PATH="$ARGUMENTS"; [ -n "$SCAN_PATH" ] || SCAN_PATH="."   # $ARGUMENTS is substituted by Claude Code; $1 is not set
cd "$SCAN_PATH" || { echo "BLOCKED: $SCAN_PATH not found"; exit 2; }
HAS_NPM=false; HAS_PIP=false; HAS_MAVEN=false; HAS_PUB=false
[ -f package.json ] && HAS_NPM=true
{ [ -f pyproject.toml ] || [ -f requirements.txt ]; } && HAS_PIP=true
[ -f pom.xml ] && HAS_MAVEN=true
[ -f pubspec.yaml ] && HAS_PUB=true
echo "npm=$HAS_NPM pip=$HAS_PIP maven=$HAS_MAVEN pub=$HAS_PUB"
```
No ecosystem detected → NOT APPLICABLE (say which manifests were looked for).

### Step 2: Run ecosystem-specific scanners

Every scanner records its OWN exit code to a log. Status per ecosystem: **PASS** (scanner ran, exit 0), **FAIL** (scanner reported findings at or above the threshold), **BLOCKED** (scanner missing, crashed or not configured). A missing tool is never "no vulnerabilities".

```bash
if [ "$HAS_NPM" = true ]; then        # NestJS / Angular / React / Node; exit 1 = findings at --audit-level
  if command -v npm >/dev/null; then npm audit --audit-level=high --json > /tmp/npm-audit.json 2>/tmp/npm-audit.err; echo "NPM AUDIT EXIT:$?"
  else echo "npm: BLOCKED (npm not installed)"; fi
fi
if [ "$HAS_PIP" = true ]; then        # exit 1 = known vulnerabilities; --strict fails on unauditable deps
  # Audit the LOCKED set. Bare `pip-audit` audits the interpreter it runs in (a uv tool venv, the global one), not this project.
  if [ -f uv.lock ]; then
    if uv export --locked --no-dev --no-hashes --no-emit-project -o /tmp/req.audit.txt > /tmp/uv-export.log 2>&1; then
      uvx --from pip-audit==2.10.1 pip-audit -r /tmp/req.audit.txt --no-deps --disable-pip --strict --format=json --desc > /tmp/pip-audit.json 2>/tmp/pip-audit.err; echo "PIP-AUDIT EXIT:$?"
    else echo "pip: BLOCKED (uv export --locked failed: stale or missing lock, see /tmp/uv-export.log)"; fi
  elif [ -f requirements.txt ]; then   # only meaningful if every line is pinned (==)
    uvx --from pip-audit==2.10.1 pip-audit -r requirements.txt --strict --format=json --desc > /tmp/pip-audit.json 2>/tmp/pip-audit.err; echo "PIP-AUDIT EXIT:$?"
  else echo "pip: BLOCKED (pyproject.toml without uv.lock: run uv lock first)"; fi
fi
if [ "$HAS_MAVEN" = true ]; then      # non-zero = CVSS >= 7 found, or plugin/NVD failure (read the log)
  if command -v mvn >/dev/null; then mvn -q org.owasp:dependency-check-maven:check -DfailBuildOnCVSS=7 -Dformat=JSON > /tmp/mvn-dc.log 2>&1; echo "DEPCHECK EXIT:$?"
  else echo "maven: BLOCKED (mvn not installed)"; fi
fi
if [ "$HAS_PUB" = true ]; then
  # There is no `pub audit` subcommand: on Flutter 3.50.1 `flutter pub audit` and `dart pub audit` exit 64
  # ("Could not find a subcommand"); 3.44.2 printed the help and exited 0, which read as a clean scan
  # (historical; not re-run on 3.50). Pub reports advisories during `pub get`
  # ("affected by advisory", dart.dev/tools/pub/security-advisories).
  if command -v flutter >/dev/null; then PUB="flutter pub"; elif command -v dart >/dev/null; then PUB="dart pub"; else PUB=""; fi
  if [ -z "$PUB" ]; then echo "pub: BLOCKED (neither flutter nor dart installed)"
  else $PUB get > /tmp/pub-get.log 2>&1; rc=$?
    if [ "$rc" -ne 0 ]; then echo "pub: BLOCKED (pub get exit $rc)"
    elif grep -qi 'advisor' /tmp/pub-get.log; then echo "pub: FAIL (advisories)"; grep -i 'advisor' /tmp/pub-get.log
    else echo "pub: PASS (no advisories reported by pub get)"; fi
  fi
fi
```
Read findings from the JSON/log files (`jq '.vulnerabilities' /tmp/npm-audit.json`, `jq '.dependencies' /tmp/pip-audit.json`, `target/dependency-check-report.json`). For a non-zero exit with no findings in the output, the scanner itself failed: BLOCKED, with the stderr tail.

### Step 3: Calculate priority scores

For each CVE found, calculate a priority score:

```
priority_score = (cvss * 0.4) + (exploitability_score * 2.0) + (fix_available ? 1.0 : 0.0)
```

Where:
- `cvss`: CVSS base score (0.0-10.0)
- `exploitability_score`: CVSS exploitability sub-score (default 2.0 if not available)
- `fix_available`: 1.0 if a patched version exists, 0.0 otherwise

Sort all findings by priority_score descending.

### Step 4: Generate CycloneDX SBOM summary

For each detected dependency, output the PURL (Package URL) format:

```
pkg:{ecosystem}/{package}@{version}
```

Examples:
- `pkg:npm/express@4.18.2`
- `pkg:pypi/fastapi@0.165.0`
- `pkg:maven/org.springframework.boot/spring-boot-starter@4.2.0`
- `pkg:pub/riverpod@3.0.0`

### Step 5: Produce final report

```
DEPENDENCY VULNERABILITY SCAN
==============================
Scanned: [path]
Ecosystems: [list of detected ecosystems]
Total vulnerabilities: [count]

IMMEDIATE ACTION REQUIRED (CVSS 9.0+):
  Priority | Package        | CVE           | CVSS | Fix Available | Fix Version
  -------- | -------------- | ------------- | ---- | ------------- | -----------
  [sorted by priority_score desc]

SHORT-TERM (CVSS 7.0-8.9):
  Priority | Package        | CVE           | CVSS | Fix Available | Fix Version
  -------- | -------------- | ------------- | ---- | ------------- | -----------
  [sorted by priority_score desc]

MONITOR (CVSS < 7.0):
  [count] lower-severity findings -- run with --all to see full list

SBOM SUMMARY (CycloneDX PURL format):
  [list of pkg:... PURLs for all dependencies]

NEXT STEPS:
  [ ] Update packages with available patches for CVSS 9+ immediately
  [ ] Review short-term findings in next sprint planning
  [ ] Run /security-hardening for comprehensive remediation
```

Use instead when: `/audit-security` — full audit (runs this as its dependency step); `/security-sast` — code-level findings.
