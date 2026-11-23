---
description: XSS sink scanner for Angular and React web apps. Detects bypassSecurityTrust* misuse, raw DOM HTML sinks, [innerHTML] bindings, React dangerouslySetInnerHTML, unsafe URLs and string-to-code. Produces framework-aware findings with DOMPurify fix patterns. Rules: security-reviewer/reference/web-frontend-security.md §1.
allowed-tools: Bash, Read, Glob, Grep
disable-model-invocation: true
---

# Web XSS Vulnerability Scan (Angular, React)

Target path: `$ARGUMENTS` (default: `src/`).

## Step 1: Scan for dangerous patterns

Run grep searches for each severity category against `*.ts`, `*.tsx`, `*.js`, `*.jsx` and `*.html` files in the target path. Keep every `--include` glob quoted (zsh expands an unquoted `*.ts`). A hit is reviewed, not automatically a finding: classify it by whether untrusted (user, API, markdown or model) data can reach it.

### CRITICAL

```bash
# Script injection bypass
grep -rnE 'bypassSecurityTrustScript\(' $ARGUMENTS --include='*.ts'
# URL injection bypass (may enable javascript: URIs)
grep -rnE 'bypassSecurityTrustUrl\(' $ARGUMENTS --include='*.ts'
# String-to-code
grep -rnE '\beval\(|new Function\(' $ARGUMENTS --include='*.ts' --include='*.tsx' --include='*.js' --include='*.jsx'
# React raw HTML (CRITICAL when the value is untrusted and not DOMPurify output)
grep -rnE 'dangerouslySetInnerHTML' $ARGUMENTS --include='*.tsx' --include='*.jsx'
```

### HIGH

```bash
# HTML injection bypass
grep -rnE 'bypassSecurityTrustHtml\(' $ARGUMENTS --include='*.ts'
# Direct DOM manipulation bypassing Angular sanitizer
grep -rnE 'ElementRef.*nativeElement.*innerHTML' $ARGUMENTS --include='*.ts'
# Direct innerHTML assignment in component code
grep -rnE 'document\..*\.innerHTML\s*=' $ARGUMENTS --include='*.ts'
# Template innerHTML binding (also inline templates in .ts)
grep -rnE '\[innerHTML\]=' $ARGUMENTS --include='*.html' --include='*.ts'
# Raw DOM sinks in any web code
grep -rnE '\.(inner|outer)HTML\s*=|insertAdjacentHTML\(|document\.write\(' $ARGUMENTS --include='*.ts' --include='*.tsx' --include='*.js' --include='*.jsx'
```

### MEDIUM

```bash
# nativeElement innerHTML in any context
grep -rnE 'nativeElement\.innerHTML' $ARGUMENTS --include='*.ts'
# bypassSecurityTrustResourceUrl (less severe but still risky)
grep -rnE 'bypassSecurityTrustResourceUrl\(' $ARGUMENTS --include='*.ts'
```

## Step 2: Report each finding

For every match, output in this format:

```
SEVERITY: [CRITICAL/HIGH/MEDIUM]
File: [path:line]
Pattern: [the detected code snippet]
Risk: XSS via unsanitized user input reaching DOM
Fix: [specific Angular-idiomatic fix from the table below]
```

### Secure alternatives

| Vulnerable Pattern | Fix |
|--------------------|-----|
| `bypassSecurityTrustHtml(val)` | Remove it. Render as text (`{{ }}`), or `DOMPurify.sanitize(val, strictConfig)` → `[innerHTML]` (Angular still sanitizes). Never bypass on user, API, markdown or model data |
| `[innerHTML]="var"` | Plain text: `{{ var }}`. HTML from markdown/model output: `marked` → `DOMPurify.sanitize` → `[innerHTML]` (`ai-chat/reference/streaming-patterns.md`) |
| `nativeElement.innerHTML = x` | Use a template binding. `Renderer2.setProperty(el, 'innerHTML', …)` is NOT sanitized either |
| `dangerouslySetInnerHTML={{ __html: x }}` (React) | Render as text, or pass only `DOMPurify.sanitize(x, strictConfig)` output |
| `bypassSecurityTrustScript(x)` | Remove entirely -- load scripts via Angular-approved methods only |
| `bypassSecurityTrustUrl(x)` | Don't bypass: Angular already sanitizes URL bindings. Only for a URL the code builds from a fixed scheme + origin + validated id |
| Any HTML rendering | Add `DOMPurify.sanitize(input)` as secondary defense before rendering |

## Step 3: Prevention checklist

Print after findings:

```
WEB XSS PREVENTION CHECKLIST (Angular, React):
[ ] Template bindings: No [innerHTML] with unsanitized user data
[ ] TypeScript: No nativeElement.innerHTML assignments
[ ] No bypassSecurityTrust* on user, API, markdown or model data
[ ] React: no dangerouslySetInnerHTML except DOMPurify output; href/src from user data parsed with new URL() and scheme-allowlisted
[ ] CSP: Content-Security-Policy header prevents inline scripts
[ ] DOMPurify: Installed and applied before any HTML rendering
[ ] No user data in template string interpolation that renders HTML tags
```

## Risk Score

Calculate: `(CRITICAL count x 10) + (HIGH count x 7) + (MEDIUM count x 4)`, capped at 100.

```
XSS RISK SCORE: [score]/100
Remediation priority: [CRITICAL findings first, then HIGH, then MEDIUM]
Total findings: [N] (CRITICAL: [n], HIGH: [n], MEDIUM: [n])
```

$ARGUMENTS
