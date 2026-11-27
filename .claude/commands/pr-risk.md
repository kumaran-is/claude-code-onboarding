---
description: "Calculate a composite PR risk score (size, complexity, test coverage, dependencies, security) before merging or reviewing. Detects large PRs needing splits and generates a context-aware pre-merge checklist. Run before /review-pr or before opening a PR. Usage: /pr-risk [branch or commit range] (default: HEAD~1..HEAD)"
allowed-tools: Bash, Read, Glob, Grep
---

# PR Risk Assessment

Calculate a composite risk score across 5 dimensions before review or merge.

## Step 1 — Determine Scope

Use `$ARGUMENTS` as the diff range if provided. Otherwise default to `HEAD~1..HEAD`.

## Step 2 — Gather Raw Data

Run all of these:

```bash
# Size stats
git diff --shortstat $SCOPE

# File list with status (A=added, M=modified, D=deleted, R=renamed)
git diff --name-status $SCOPE

# Dependency file changes
git diff --name-only $SCOPE | grep -E "package\.json$|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|requirements\.txt|uv\.lock|Pipfile\.lock|pom\.xml|build\.gradle|pubspec\.yaml|pubspec\.lock"

# Security-sensitive file changes
git diff --name-only $SCOPE | grep -iE "auth|login|token|jwt|crypto|secret|password|credential|permission|role|guard|interceptor|middleware|\.env|config/.*\.(yml|yaml|json)"

# Full diff for pattern analysis
git diff $SCOPE
```

## Step 3 — Score Each Factor (0–10)

### A. Size Risk

Use the higher of the file-count score and the line-count score.

| Score | Files changed | OR total lines changed |
|-------|--------------|----------------------|
| 0–2   | ≤ 5          | ≤ 100                |
| 3–4   | ≤ 10         | ≤ 300                |
| 5–6   | ≤ 20         | ≤ 600                |
| 7–8   | ≤ 40         | ≤ 1,000              |
| 9–10  | > 40         | > 1,000              |

### B. Complexity Risk

Start at 0. Add points for each signal found in the diff. Cap at 10.

| Signal in diff | Points |
|----------------|--------|
| Public interface or API contract changed (endpoint signature, DTO field, exported function) | +2 |
| Database schema or migration file added or modified | +3 |
| Auth, security, permission, or role logic changed | +3 |
| Async or concurrent code added or modified | +2 |
| New third-party integration added | +2 |
| CI/CD, Docker, or infrastructure config changed | +1 |
| Cross-cutting concern modified (logging, error handler, event bus, interceptor) | +1 |

### C. Test Coverage Risk

Count files in the diff:
- **Source files**: `.ts`, `.java`, `.py`, `.dart`, `.kt`, `.swift`, `.js` — excluding test files
- **Test files**: paths containing `test`, `spec`, `__tests__`, `_test.`, `.test.`, `.spec.`

```
test_ratio = test_files_changed / max(source_files_changed, 1)
```

| Score | test_ratio |
|-------|-----------|
| 0–1   | ≥ 1.0 (at least one test per source file) |
| 2–3   | 0.5–0.99  |
| 4–5   | 0.2–0.49  |
| 6–7   | 0.01–0.19 |
| 8–10  | 0 (no test files changed despite source changes) |

If no source files changed (docs-only, config-only), score = 0.

### D. Dependency Risk

| Score | Criteria |
|-------|----------|
| 0     | No dependency files changed |
| 2     | Lock file changed only (auto-generated, no manifest change) |
| 4     | Package manifest changed — patch or minor bumps only |
| 6     | New direct dependency added |
| 8     | Major version bump OR dependency removed |
| 10    | Unverified source, fork, or git-URL dependency |

### E. Security Risk

Start at 0. Add points for each signal. Cap at 10.

| Signal | Points |
|--------|--------|
| Auth / login / session / token handling changed | +3 |
| JWT, OAuth, or credential logic changed | +3 |
| Input validation or sanitization changed | +2 |
| SQL query construction changed (risk of injection) | +2 |
| New public endpoint or new response field exposed | +1 |
| Environment variable or secrets config changed | +2 |
| CORS, rate-limiting, or firewall rules changed | +2 |

## Step 4 — Calculate Overall Score

```
overall = (size + complexity + test_coverage + dependency + security) / 5
```

| Overall | Level | Required action |
|---------|-------|----------------|
| < 3.0   | 🟢 Low      | Standard review, one approver |
| 3.0–5.9 | 🟡 Medium   | Thorough review recommended |
| 6.0–7.9 | 🟠 High     | Two reviewers + test evidence required |
| ≥ 8.0   | 🔴 Critical | Tech lead sign-off before merge |

## Step 5 — Large PR Detection

If `files_changed > 20` OR `total_lines > 1,000`:

1. Flag as **⚠️ Large PR** — harder to review, higher defect rate
2. Group changed files by feature area (top-level package, module, or directory)
3. Suggest logical split boundaries based on those groupings
4. Provide the split workflow:

```bash
# Split into focused PRs
git checkout -b <base-branch>/<part-n>
git cherry-pick <commit-hashes-for-this-part>
git push origin <base-branch>/<part-n>
# Open PR for this part, then repeat for remaining parts
```

## Step 6 — Context-Aware Pre-Merge Checklist

Generate only the sections that apply to what changed.

**Always:**
- [ ] Self-review done — read the full diff as if it's someone else's code
- [ ] No debug statements (`console.log`, `print`, `System.out.println`, `debugPrint`, `logger.debug` in prod paths)
- [ ] No hardcoded credentials, API keys, or tokens
- [ ] CI is green (or would pass with these changes)

**If source files changed:**
- [ ] No functions > 50 lines introduced
- [ ] No nesting deeper than 4 levels
- [ ] All catch blocks log the error and rethrow or return error state (no silent swallows)
- [ ] No duplicate logic — checked against shared utilities

**If test_ratio < 0.5 or no test files changed:**
- [ ] New logic has at least one test for the happy path
- [ ] At least one error condition is tested
- [ ] Tests are deterministic (no sleep, no Date.now() in assertions)

**If auth / security files changed:**
- [ ] No SQL string concatenation (parameterized queries only)
- [ ] Input validated at system boundary (not deep inside service)
- [ ] New routes/endpoints have authorization checks
- [ ] No sensitive data (tokens, passwords) written to logs

**If dependency files changed:**
- [ ] New package has active maintenance (check npm/PyPI/pub.dev)
- [ ] No known CVEs: run `npm audit --audit-level=high` / `pip-audit --strict` / `flutter pub get` advisories (there is no `pub audit` subcommand)
- [ ] License is compatible with project

**If database migration files changed:**
- [ ] Migration has a down/rollback path
- [ ] No data-destructive operation without explicit backup step noted
- [ ] Index strategy reviewed for expected query patterns

**If CI/CD or infrastructure config changed:**
- [ ] Secrets are referenced from vault/env, not hardcoded
- [ ] Change is tested in non-production environment first
- [ ] Rollback plan exists

## Output Format

```
## PR Risk Assessment: <scope>

**Overall Risk**: 🟡 Medium (5.2 / 10)
**Recommendation**: Thorough review recommended — two reviewers preferred.

### Risk Factors

| Factor         | Score  | Key Signal                                |
|----------------|--------|-------------------------------------------|
| Size           |  4/10  | 8 files, 210 lines changed                |
| Complexity     |  6/10  | API contract + async code modified        |
| Test Coverage  |  5/10  | ratio 0.38 (3 test / 8 source files)      |
| Dependencies   |  3/10  | Lock file updated, no manifest change     |
| Security       |  8/10  | Auth middleware + JWT handling changed    |

**Risk drivers**: Security (8), Complexity (6) — address these first.

### Mitigation
- **Security (8)**: Have a second reviewer read the auth middleware diff line-by-line.
- **Complexity (6)**: Verify async edge cases (timeout, rejection) have test coverage.

### Large PR: NO (8 files, 210 lines)

### Pre-Merge Checklist

[generated checklist sections based on what changed]

---
Next: run /review-pr for the 6-role qualitative review.
```

Use instead when: `/create-pr` — the same score embedded in a PR body with the `gh` command; `/review-pr` or `/review-code` — the actual review. A risk score is not a gate: `/verify pre-pr` is.

$ARGUMENTS
