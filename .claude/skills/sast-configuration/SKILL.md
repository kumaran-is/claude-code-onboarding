---
name: sast-configuration
description: "Static Application Security Testing (SAST) configuration skill. Use when setting up security scanning, configuring Semgrep rules, running SAST in CI/CD, reviewing SAST findings, or writing custom security rules. Triggers: SAST, static analysis, Semgrep, Bandit, ESLint security, code scanning, vulnerability detection, security scan setup."
allowed-tools: Read, Grep, Glob, Bash
metadata:
  triggers: SAST, static analysis, Semgrep, security scanning, static code analysis, security rules, Bandit, gosec
  related-skills: security-reviewer, threat-modeling, code-reviewer
  domain: security
  role: specialist
  scope: infrastructure
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law: NO SAST CONFIGURATION WITHOUT READING THE CUSTOM RULES FILE FIRST

Read `references/semgrep-custom-rules.md` before writing or modifying any SAST configuration.

## When to Use

- Setting up scanning for a new service → tool selection + config templates
- Writing or modifying Semgrep rules → custom rules reference
- Integrating SAST into CI/CD → GitHub Actions example in tool config
- Triaging SAST findings → risk scoring and false positive suppression

## Process

1. **Detect languages** — Check for `pom.xml` (Java), `package.json` (TS), `pyproject.toml` (Python), `pubspec.yaml` (Dart)
2. **Load custom rules** — Read `references/semgrep-custom-rules.md` for project-specific rules already in place
3. **Select tools** — Java → SpotBugs + Semgrep; TS/Angular/NestJS → ESLint security + Semgrep; Python → Bandit + Semgrep; Dart → dart analyze
4. **Configure** — See `references/sast-tool-config.md` for config file templates and CI/CD step
5. **Run and triage** — Execute `/security-sast [path]`, classify findings, suppress false positives per the suppression patterns in tool config

## References

| File | Content |
|------|---------|
| `references/semgrep-custom-rules.md` | 10 custom Semgrep rules for Java/TS/Python, usage, suppression syntax |
| `references/sast-tool-config.md` | Tool comparison matrix, config templates (Bandit/.bandit, ESLint, dart analyze, Semgrep CI), risk scoring thresholds |

## Error Handling

If a scanner is not installed, report the install command from the tool config reference rather than skipping the scan silently.
