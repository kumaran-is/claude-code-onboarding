---
name: silent-failure-hunter
description: Audits error handling for swallowed exceptions, empty catch blocks, unjustified fallbacks, and mock data returns on failure. Use after implementing features with API calls, database operations, or any I/O that can fail. Enforces code-standards.md "No Silent Failures" rule.
allowed-tools: Read, Grep, Glob, Bash
agent: silent-failure-hunter
context: fork
metadata:
  triggers: error handling, catch block, silent failure, swallowed exception, fallback, empty catch, return null on error, review error handling
  related-skills: error-detective, security-reviewer, code-reviewer
  domain: quality
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-03-16"
---

## Iron Law

An empty catch block is not error handling — it is a lie to the operator. Every catch must log AND rethrow or return an error state.

# Silent Failure Hunter

Enforces the "No Silent Failures" rule from `code-standards.md` — every catch block must log the error AND either rethrow or return an explicit error state. Finds swallowed exceptions, fallbacks that hide failures, and mock data returned on error.

## When to Use

- After implementing features with API calls or database operations
- Reviewing any code that has try/catch blocks
- Before merging code that touches external service integrations
- Proactively after implementing I/O-heavy features

## Forbidden Patterns (all languages)

```
catch (e) { return []; }           // Silent empty return
catch (e) { return MockData.x; }   // Fake data on failure
catch (e) { /* nothing */ }        // Swallowed exception
catch (e) { log.error(e); }        // Log only, no rethrow
```

## Required Pattern

```
catch (e) {
  logger.error('fetchData failed', context);
  rethrow; // OR throw ServiceException / return Result.failure
}
```

## Stack-Specific Patterns to Grep

| Stack | Forbidden grep pattern |
|-------|----------------------|
| Java/Spring | `onErrorReturn(` without prior log, `switchIfEmpty(Mono.empty())` |
| NestJS | `catch.*return null`, empty catch blocks |
| Python | `except.*pass`, `except.*return \[\]` |
| Flutter | `catch.*\{\s*\}`, `on Exception.*return null` |

## Severity Levels

| Level | Meaning |
|-------|---------|
| **CRITICAL** | Silent failure — error occurs with no log and no user feedback |
| **HIGH** | No user feedback / unjustified fallback |
| **MEDIUM** | Missing context in log / overly broad catch with log |

## Output Format

```
## Silent Failure Audit: [scope]

### CRITICAL
[file:line] — [description of silent failure]
Hidden errors: [types that could be suppressed]
Fix: [corrected code]

### Summary
- Issues: N (critical: X, high: Y, medium: Z)
- Verdict: PASS / FAIL
```
