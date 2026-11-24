# Leverage Patterns

Always-loaded mandates only. The procedures, templates and tables behind them load on demand:
- `.claude/skills/plan-mode-review/reference/execution-patterns.md`: task protocol detail, declarative goals, three-pass development, adaptive depth, autonomy ladder, error-recovery templates, change-request tree.
- `.claude/skills/subagent-driven-development/reference/orchestration-and-context.md`: project-creation pre-flight, skill and agent selection with trigger-word modes, model choice, foreground/background, context-window management and the summary template, sub-agent governance, orphan prevention.

## Task Response Protocol

UNDERSTAND (restate, flag ambiguity) → PLAN (3–5 steps, each with `→ verify:`) → DECISIONS (choices and trade-offs) → IMPLEMENT (simplest correct solution) → VERIFY (dead code, unused imports, unrelated changes, edge cases) → REPORT. Compress small tasks, but never skip UNDERSTAND or VERIFY. Non-trivial changes (architecture, multi-service, schema): `/plan-review`, then save the approved plan to `docs/plans/YYYY-MM-DD-<feature>.md` before implementing.

Plans, task subjects, dispatch prompts and PR descriptions name counts and items ("add 4 tests: [happy path, expired token, missing token, invalid signature]"), never vague categories ("add some tests"). If you cannot name the items, clarify the scope first.

Trigger words set the mode: "what if / options / compare" → `/brainstorm`, no code yet; "not working / error / failing" → `/debug` (root cause before fixes); "review / check / audit" → the stack's reviewer agent; "deploy / ship / ready to merge" → `/ship`. Mixed signals: ask which to start with.

## Test-First

Write the test that defines success before the code, implement until it passes, show both; which tests each kind of change needs: `first-principles.md` Layer 2. Correctness first; optimize only a profiled bottleneck, measured before and after.

## Project Creation

Run the scaffold command (`/scaffold-<stack>`) in the main session BEFORE spawning any agent: sub-agents run headlessly and they **cannot** invoke slash commands, and `block-raw-scaffold.sh` blocks raw `flutter create`, `ng new`, `nest new`, `create-vite`, `create-next-app` and `create-react-router`. Never prefix an ad-hoc creator call with `CC_SCAFFOLD=` to get past the hook. Check the scaffold's key directories exist, then start every agent task with a "PROJECT ALREADY SCAFFOLDED" header naming the absolute path.

## Sub-Agents

Default: do it yourself. Use sub-agents for parallel independent work, a plan with 3+ tasks (`subagent-driven-development`), or specialist review (the reviewer table in `.claude/SKILLS_GUIDE.md`). Before dispatching ANY agent:
1. Plan-driven implementation → load `subagent-driven-development` first (Implementer → Spec Reviewer → Quality Reviewer).
2. Pass explicit context in the prompt: task, file paths, decisions. Explore and Plan agents (and any agent with `omitClaudeMd`) start without CLAUDE.md and `.claude/rules/`: paste the rules they need.
3. Pick a `subagent_type` that can do the work: read-only agents cannot edit files.
4. Use `isolation: "worktree"` for changes that may conflict with concurrent work.

Agent output is invisible to the user: summarize it. Agent Teams: send each teammate `shutdown_request`, then `TeamDelete`.

## Live Browser in the Loop

For **web** targets, validate against the rendered page, not just static code: Playwright CLI drives it, `@playwright/test` makes the check repeatable, Chrome DevTools MCP is for performance and diagnostics. Flutter Android/iOS apps are validated with Maestro. Routing: `.claude/rules/testing-tool-selection.md`.

## Failure Handling

- Clear signal (failing test with stack trace, lint error with file:line, CI log): fix it, run the tests, show the diff. Ambiguous signal ("it's slow", no reproduction): ask first (`core-behaviors.md` §10).
- Never silently skip a failed step and claim done: report what stopped, what completed, and the options. Never classify an error as Low when it hides a real problem.
- The user changes direction mid-task: stop, list what is done (file:line) and not started, confirm keep / modify / revert, then switch.
- Context: read selectively (grep first, then `offset`/`limit`), never re-read unchanged files, and at ~70–80% of the window summarize with the template in the orchestration reference.
