# First Principles — Session Invariants

This file is the **numeric enforcement layer** on top of `core-behaviors.md`.
Where core-behaviors gives guidance, this file gives measurable pass/fail gates.

**Precedence:** This file sits between `core-behaviors` and `code-standards`.
When a rule here conflicts with `code-standards`, this file wins.

---

## Layer 1 — Hard Constraints

These are absolute. No exceptions, no judgment calls. Violation = stop immediately and report.

### Data Safety
- `DROP`, `DELETE`, `TRUNCATE` on any table → **STOP. Get explicit approval first.**
- Modifying a production database directly → **STOP. Migrations only.**
- Committing `.env`, `*.pem`, `*.key`, `credentials.*` → **STOP. Use environment variables.**

### Code Safety
- Pushing directly to `main` or `develop` → **STOP. PR only.**
- Skipping tests to ship faster → **STOP. Tests are not optional.**
- Using `as any` in NEW TypeScript code → **STOP. Add a proper type.**
- `console.log` / `console.warn` / `console.error` in new production TypeScript → **STOP. Use Logger.**
- `print()` in new Python production code → **STOP. Use structured logger.**

### Scope Safety
- Touching files outside the stated task → **STOP. Ask first.**
- Refactoring adjacent code while fixing a bug → **STOP. Separate PR.**
- Deleting pre-existing code you don't fully understand → **STOP. Ask first.**

---

## Layer 2 — Quality Thresholds

Numeric gates. Binary pass/fail. No "mostly" or "almost".

### Test Coverage (per session)
| What changed | Required |
|---|---|
| New feature or new logic | ≥ 1 test for happy path + ≥ 1 test for primary error path |
| Bug fix | ≥ 1 test that reproduces the bug before the fix |
| Refactor | All existing tests pass before AND after — no new tests required |
| Config / rename / trivial | Existing tests pass — no new tests required |

**Measurement:** Run the test suite. Show pass/fail count. "Looks right" is not evidence.

### Type Safety (TypeScript — NestJS + Angular)
| Metric | Threshold | How to check |
|---|---|---|
| New `as any` introduced | **0** | `grep -c "as any" <changed files>` |
| New `: any` parameters | **0** | `grep -c ": any\b" <changed files>` |
| `eslint-disable` added | **0** (unless justified in PR comment) | `grep -c "eslint-disable" <changed files>` |

### Type Safety (Dart — Flutter)
| Metric | Threshold | How to check |
|---|---|---|
| New `dynamic` without justification | **0** | `grep -c "\bdynamic\b" <changed dart files>` |
| Flutter analyzer errors | **0** | `flutter analyze` exit code = 0 |
| Flutter analyzer warnings introduced | **0 new** | Compare warning count before/after |

### Error Handling
| Metric | Threshold | How to check |
|---|---|---|
| Bare `catch(e) {}` (swallowed) | **0** | `grep -c "catch.*{[[:space:]]*}" <changed files>` |
| `catch` without log + rethrow/error-state | **0** | Review every new catch block |
| Python bare `except:` | **0** | `grep -c "except:" <changed py files>` |

### Commit Discipline
| Metric | Threshold |
|---|---|
| Files changed in one commit | ≤ 15 (larger = split first) |
| Unrelated files in same commit | 0 |
| TODO / FIXME in new code | 0 (either do it or create a task) |

### Security (when changed files touch auth, crypto, input handling, file uploads)
| Gate | Threshold |
|---|---|
| `security-reviewer` agent verdict | No CRITICAL or HIGH unresolved |
| Passwords stored/compared as plaintext | 0 |
| SQL built via string concatenation | 0 |
| User input used without validation | 0 |

---

## Layer 3 — Workflow Invariants

Sequencing rules. These define what must happen before/after key actions.

```
Before writing code:
  → Assumptions surfaced (core-behaviors §1)
  → MCP consulted for the relevant framework (code-standards.md)

Before opening a PR:
  → /ship gate passed (all items green)
  → Change description written (CHANGES MADE / DIDN'T TOUCH / CONCERNS)

Before any architecture change:
  → ADR created first, code second
  → /design-architecture or @architect used

After any correction by the user:
  → Lesson written to lessons.md BEFORE continuing work

After any refactor:
  → Dead code created by YOUR changes removed immediately
  → Pre-existing dead code: list it, ask before removing
```

### Additional Invariants

**No unsolicited documentation.**
Never create `.md` files, reports, READMEs, diagrams, or summaries unless the human
explicitly asks for them. Proactively generating docs no one requested is scope creep.
Exceptions (mandatory writes, not unsolicited): `lessons.md` entries (CLAUDE.md self-improvement
loop), an approved plan saved to `docs/plans/` (`leverage-patterns.md`), and the ADR the
Architecture Gate requires (`verification-and-reporting.md`).

**3-attempt hard stop.**
If you have tried the same approach ≥ 3 times and it keeps failing: STOP.
Do not try a 4th time. Instead, report:
```
STUCK after 3 attempts at [approach]:
- Attempt 1: [what you tried, what failed]
- Attempt 2: [what you tried, what failed]
- Attempt 3: [what you tried, what failed]
Options:
A) Different approach: [describe]
B) Escalate to human — need more context
```
Looping on the same broken approach wastes tokens and hides the real problem.

**Edit fallback protocol.**
If the Edit tool fails twice on the same file (wrong old_string, merge conflict, etc.):
1. After 2nd failure: switch to `Bash` with `sed`/`awk` for the specific change
2. If Bash approach also fails: use Write tool to recreate the entire file
3. Always verify the final file content after a fallback write
Never silently retry Edit a 3rd time — escalate the tool instead.

---

## Layer 4 — AI Anti-Pattern Detection

Named, detectable failure modes specific to LLMs. Flag these in self-review before reporting done.

### Hallucinated API
**What:** Code uses a method, parameter, or class that doesn't exist in current docs.
**Detection:** Does every API call have MCP-verified evidence from this session?
**Fix:** Query MCP for the method signature. If it doesn't exist, find the real one.

### Stale Context Drift
**What:** A decision made in this conversation is contradicted by new code without acknowledgment.
**Detection:** Does this code conflict with any ASSUMPTION I stated earlier this session?
**Fix:** Acknowledge the conflict explicitly. Ask which takes precedence.

> **Removed anti-patterns** (covered elsewhere): Confidence Without Evidence → `verification-and-reporting.md`; Sycophancy Drift → `core-behaviors.md §3`; Premature Abstraction → `code-standards.md Rule of Three`; Scope Creep → `core-behaviors.md §5`; Over-Apology → default Claude behavior.

---

## Self-Check Before Reporting Done

→ **Use the Quality Gates in `verification-and-reporting.md`.** They are the single canonical completion checklist. The gates enforce Layers 1–4 of this file plus workflow-specific requirements. If ANY gate item is NO → do not say "done".
