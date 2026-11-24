# Code Standards

## Documentation Before Code

Consult official docs via MCP before writing ANY code. This rule is enforced here (always-loaded). Custom and general-purpose subagents inherit these rules; the built-in Explore and Plan subagents start without CLAUDE.md and rules, so paste what they need into their prompt.

```
About to write code?
    |
    +-- Does a dedicated MCP server exist for this library/framework?
    |   YES -> Query it first. Use the response to inform your implementation.
    |   NO  -> Use Context7 MCP as fallback.
    |
    +-- Does the code use an API you haven't verified this session?
    |   YES -> Check signature, params, return type against MCP/docs before using.
    |   NO  -> Continue.
    |
    +-- Does this change touch the database (schema, queries, migrations)?
    |   YES -> Follow postgres-best-practices. Run `postgresql-database-reviewer` agent.
    |   NO  -> Continue.
    |
    +-- Is this the simplest correct solution?
        NO  -> Simplify before proceeding. Re-read core-behaviors.md §4.
        YES -> Proceed.
```

**Non-negotiable:**
- NEVER generate code from memory when an MCP server can confirm the current API
- NEVER use deprecated methods — MCP results will show current alternatives
- If MCP returns something different from what you expected, trust the MCP result

**Dependency version selection:**
- When selecting a dependency, explicitly use the latest stable version. Pin to a specific version in `package.json` / `pubspec.yaml` / `pom.xml` / `pyproject.toml` — never use `*`, `latest`, or unpinned ranges in production.
- Verify the package exists and is legitimate before installing (see `security-review-checklist.md` §6 Dependencies).

**MCP lookup order:**
1. Dedicated MCP server listed in the skill's SKILL.md (e.g., Angular CLI MCP, Firebase MCP, Dart MCP)
2. `Context7` MCP — resolve library ID first, then query docs
3. `WebSearch` / `WebFetch` — last resort for very new or niche libraries

## Modify Existing Files First

```
Need to add code?
    ↓
Does relevant file exist?
    ├─ YES → Modify existing file (DEFAULT)
    └─ NO → Is this >150–200 lines of cohesive new logic?
              ├─ YES → Consider new file (ask human first)
              └─ NO → Find closest existing file and add there
```

When creating new files: remove/update old files, update all imports, delete orphans. NEVER leave old + new both existing.

### New File Justification (mandatory before creating any file)

Before creating a new file, state explicitly:
1. Which existing files were checked and found unsuitable
2. Why they could not be extended or reused
3. Why the new file is necessary for this specific task

Every new file must have a clear purpose that traces directly to the requested change. Creating a new file to avoid understanding the existing structure is not acceptable. A new file the request did not call for needs approval first (`core-behaviors.md` §5, RED).

## Error Handling

### No Silent Failures, No Mock Data, No Fallbacks

```
// ❌ FORBIDDEN (applies to ALL languages)
catch (e) { return []; }           // Silent empty return
catch (e) { return MockData.x; }   // Fake data
catch (e) { /* nothing */ }        // Swallowed exception

// ✅ REQUIRED
catch (e) {
  logger.error('fetchData failed', error: e);
  rethrow; // OR return error state (Result.failure, HttpException, HTTPException, etc.)
}
```

- Every catch block MUST log the error
- Every catch block MUST either rethrow OR return an error state
- User MUST see when something fails (snackbar, error widget, toast, etc.)
- NEVER return empty list/null/default on error
- NEVER create mock data unless explicitly requested
- Language-specific patterns: see each technology's skill (e.g., `java-spring-api`, `nestjs-api`, `python-dev`, `flutter-mobile`)

## DRY Enforcement

Before writing ANY code:

1. CHECK: Does this logic exist in shared/common utilities? → YES: import it
2. ASK: Will another module need this? → YES: create in shared utilities first

**Forbidden:** inline utility logic when shared version exists; duplicating logic across files.

| Metric | Target | Action |
| ------ | ------ | ------ |
| File size | ~400–500 lines | Extract when hard to navigate |
| Duplicate code blocks | 0 | Extract to shared |
| Inline utilities | 0 | Move to shared |

### Rule of Three — Abstraction Threshold

Use this to decide WHEN to create a shared utility or abstraction:

| Occurrences | Action |
|-------------|--------|
| 1 use | Inline — no abstraction |
| 2 uses | Accept the duplication — abstracting now is premature |
| 3+ uses | Create a shared utility/service — abstraction is justified |

**Why:** Abstracting at 1-2 uses means guessing at the right interface. At 3 uses, the pattern is proven and the correct abstraction is usually obvious.

**Exception:** If a shared utility is already < 50 lines AND is used consistently across the codebase, extracting at 2 uses is acceptable — but not required.

**Code review check:** Before approving a new helper, service, or base class, ask: "Is this abstraction backed by 3+ actual use cases today?" If not, inline it.

## Logging Standards

- **Structured:** All logs include context (user type, action, timestamp)
- **Centralized:** Single logging utility used everywhere
- **Leveled:** Appropriate levels (debug, info, warn, error)
- Log all error conditions with full context
- Log sync operations (start, success, failure)
- NEVER log sensitive data (passwords, tokens, PII)
- No `print()` or `console.log` in production code — enforced as a hard STOP in `first-principles.md` Layer 1

## Output Quality

- No bloated abstractions or premature generalization
- No clever tricks without comments explaining why
- Match the project's idioms — don't introduce a different paradigm mid-file
- Meaningful variable names (no `temp`, `data`, `result` without context)
- Zero: deprecated APIs, stub implementations, TODO comments, duplicate implementations, backward compatibility wrappers
- Tests that depend on time inject a fixed clock; before calling a failure flaky, check whether it depends on time of day, date or timezone
- Moving code moves its comments too, including suppression markers (`// ignore-*`, `# noqa`, `// pw-advisory-ok:`); compare gate results before and after the move

## Change Descriptions

After any modification:

```
CHANGES MADE:
- [file]: [what changed and why]

THINGS I DIDN'T TOUCH:
- [file]: [intentionally left alone because...]

POTENTIAL CONCERNS:
- [any risks or things to verify]
```

## Content Validation

Validate diagram syntax before writing. Test renders in target environment.

## Performance

Never optimize without evidence. Profile first.

- Use DevTools (Chrome for Angular, Flutter DevTools for mobile, JProfiler/VisualVM for Java) before assuming a bottleneck
- Follows the naive-then-optimize pattern: correct first, then profile, then optimize the proven bottleneck
- Quantify improvements: "Reduced load time from 1200ms to 400ms" not "made it faster"
- No premature optimization — measure before and after, or don't optimize
- Database queries: use `EXPLAIN ANALYZE` before rewriting. Verify index usage

## Security and Accessibility Baseline

These rules apply to ALL code changes — not just when a reviewer agent is dispatched.

### Security

- All API endpoints MUST validate and sanitize inputs
- Never trust client-side data — validate server-side
- No secrets, keys, or credentials in code — use environment variables
- Parameterized queries only — no string concatenation for SQL
- Encode output to prevent XSS (use framework defaults, never bypass)
- Authentication and authorization checks on every protected endpoint
- Passwords MUST be hashed (bcrypt cost>=12 or argon2) — never store or compare plaintext
- File uploads MUST be validated (type, size, content) and size-limited — never accept unbounded uploads

### Accessibility

- All UI changes must follow WCAG 2.2 AA (canonical checklist: `.claude/skills/accessibility-audit/reference/wcag22-checklist.md`); automated tools never prove conformance
- Semantic HTML (Angular) / proper widget semantics (Flutter)
- Interactive elements must be keyboard-navigable and screen-reader accessible
- Color contrast ratio >= 4.5:1 for normal text, >= 3:1 for large text
- Target size: >= 24×24 CSS px is the WCAG 2.2 AA minimum; house standard 44px (web) / 48dp (Flutter)

## Pre-Submit Checklist

→ **Use the Quality Gates in `verification-and-reporting.md`.** They are the single canonical checklist for all workflow types (Feature/PR, Architecture, Database, UI, Release).
