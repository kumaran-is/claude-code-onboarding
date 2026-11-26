# Orchestration and Context Playbook

Detail behind the always-loaded mandates in `.claude/rules/leverage-patterns.md` (project creation, sub-agents, context). Moved here verbatim so it loads on demand instead of in every session and every subagent. Companion: `.claude/skills/plan-mode-review/reference/execution-patterns.md` (task protocol, depth, recovery).

## Orchestrator Pre-Flight — Project Creation

When any task involves creating a **new project** (trigger words: "create", "build", "scaffold",
"new project", "start" + any tech name), the orchestrator MUST follow this sequence.

### Why this matters
Slash commands (`/scaffold-flutter-app`, `/scaffold-angular-app`, etc.) are processed by the
interactive Claude Code shell. Sub-agents run headlessly — they **cannot** invoke slash commands.
If anyone runs a raw `flutter create`, `ng new`, `nest new`, `create-vite`, `create-next-app` or `create-react-router`, the `block-raw-scaffold.sh` hook
hard-blocks the tool call with exit 2. The scaffold commands themselves run the creator with an inline
per-command marker (`CC_SCAFFOLD=<scaffold-command-name> <creator> ...`), which the hook allows for that
one command only and records in `.git/claude-state/scaffold-audit.log`. Do not add the marker to ad-hoc
creator calls; run the scaffold command instead.

### Required sequence

```
STEP 1 — Run scaffold in THIS session (mandatory, before spawning any agents)
──────────────────────────────────────────────────────────────────────────────
Tech requested          → Skill tool call (in main session only)
─────────────────────── ─────────────────────────────────────────
Flutter / Dart          → skill: "scaffold-flutter-app",  args: "<name>"
Angular                 → skill: "scaffold-angular-app",  args: "<name>"
React (Vite SPA)        → skill: "scaffold-react-app",    args: "<name>"
NestJS                  → skill: "scaffold-nestjs-api",   args: "<name>"
Python / FastAPI        → skill: "scaffold-python-api",   args: "<name>"
Java / Spring Boot      → skill: "scaffold-spring-api",   args: "<name>"
Agentic AI              → skill: "scaffold-agentic-ai",   args: "<name>"
MCP server (TypeScript) → skill: "scaffold-mcp-server",   args: "<name> [stdio|http|both]"

STEP 2 — Verify scaffold output before writing agent task files
──────────────────────────────────────────────────────────────────────────────
Check that tech-specific key directories exist, e.g.:
  Flutter  → lib/design_system/, lib/core/di/, lib/features/
  Angular  → src/app/core/, src/app/features/, src/app/design-system/
  React    → src/app/, src/features/, src/shared/
  NestJS   → src/common/, src/config/, src/modules/
  MCP      → src/, test/
If missing → scaffold did not complete — do NOT spawn agents yet.

STEP 3 — Spawn agents with "PROJECT ALREADY SCAFFOLDED" header
──────────────────────────────────────────────────────────────────────────────
Every agent task file MUST begin with:

  ## ⚠️ PROJECT ALREADY SCAFFOLDED
  The project at `<absolute-path>` was created by the orchestrator.
  DO NOT run flutter create / ng new / nest new / create-vite / create-next-app / any project-init command.
  Add files to the existing structure — never recreate it.
```

### What NOT to do
- ❌ Tell a sub-agent to run `/scaffold-flutter-app` as a bash command — it will fail silently
- ❌ Tell a sub-agent to use the Skill tool for scaffold — sub-agents don't have slash command context
- ❌ Skip the scaffold and let agents use `flutter create` — the hook will block it
- ✅ Run the Skill tool yourself in the main session, then hand the scaffolded path to agents

---

## Skill and Agent Selection

Skills and agents are lazy-loaded. The authoritative technology → skill / agent / command mapping is the **Routing** table in `.claude/SKILLS_GUIDE.md`, and the reviewer mapping is its **Reviewer agents by domain** table; this section adds only the selection rules. (Explore and Plan subagents do not load it either: paste the row they need into their prompt.)

**Rule:** Load the skill BEFORE writing code, not after. Skills contain patterns, templates, and MCP server references that prevent mistakes. Cross-cutting: debugging → `systematic-debugging`; plan review → `plan-mode-review`; test tooling per target → `testing-tool-selection.md`.

### Auto Mode Detection — Trigger Words → Behavior

When a request contains these trigger words, adopt the corresponding behavior automatically. No announcement needed — just behave accordingly.

| Trigger words in request | Mode | Behavior |
|--------------------------|------|----------|
| "what if", "options", "alternatives", "explore", "compare", "should we use", "which approach", "evaluate this idea", "should we build" | **BRAINSTORM** | Use `/brainstorm` — ≥3 options with trade-offs, Mermaid diagram, no code yet. Load `titan-methodology` skill for scoring when evaluating product/feature ideas. |
| "build", "create", "add", "implement", "write", "scaffold" | **IMPLEMENT** | Code first, no tutorial prose or comments, no over-engineering (`core-behaviors.md §4`); report with the change description from `code-standards.md` plus evidence, nothing more |
| "not working", "error", "bug", "failing", "broken", "crash", "exception", "why does" | **DEBUG** | Use `/debug` — load `systematic-debugging`, root cause first, no fixes before investigation |
| "review", "check", "audit", "is this right", "look at" | **REVIEW** | Load tech-specific reviewer agent, severity-bucketed findings |
| "explain", "how does", "what is", "teach me", "help me understand" | **TEACH** | Fundamentals first, analogy, example, then technical detail |
| "deploy", "release", "ship", "production", "ready to merge" | **SHIP** | Run `/ship` — full pre-deploy gate across all stacks |

**Important:** These are defaults, not locks. If the request mixes signals (e.g. "explain then build"), acknowledge both and ask which to start with.

### When to Dispatch a Reviewer Agent

Reviewer agents run AFTER code is written, matched by the changed files' domain using the **Reviewer agents by domain** table in `.claude/SKILLS_GUIDE.md`. Security-sensitive changes (auth, crypto, input handling) always add `security-reviewer`.

**Rule:** When in doubt, dispatch `code-reviewer`. It covers all languages. Stack-specific reviewers add deeper checks but are not a replacement — use both for critical changes.

### Common Mistakes

- Loading a skill after already writing code → patterns were missed, rewrite likely
- Dispatching a reviewer for the wrong stack → shallow review, false confidence
- Skipping skill load for "small changes" → small changes to Spring WebFlux or Riverpod still need the skill's patterns to avoid framework-specific traps

## Cost and Context Awareness

Every tool call, agent dispatch, and file read consumes tokens. Be deliberate.

### Model Selection for Sub-Agents

The Agent tool accepts a `model` parameter. Use it:

| Model | When to Use | Examples |
|-------|-------------|---------|
| **haiku** | Quick, straightforward tasks with clear instructions | File search, simple grep, formatting, linting check |
| **sonnet** | Default — implementation, orchestration, `/next`, `/ralph-loop`, `/verify` | Code generation, test writing, defect remediation |
| **opus** | Independent LLM review and quality assessment | Spec review, quality/stack reviewers, security review, architecture review |

**Default:** Inherit parent model (omit param) for implementers. Named reviewer agents declare `model: opus` in `.claude/agents/*.md`; SDD spec review (general-purpose) must pass `model: opus`. Do not override implementers onto opus.

### Foreground vs Background Agents

| Mode | When to Use |
|------|-------------|
| **Foreground** (default) | You need the result before proceeding — research, analysis, blocking question |
| **Background** | Genuinely independent work — linting, test runs, reviews while you implement |

**Rule:** Do not run agents in background just to appear fast. If you need the result to decide your next step, run in foreground.

**No completion notice?** Before re-dispatching a background agent that seems to have finished silently, read its output file or transcript (the path the dispatch returned). A second dispatch repeats the work and, with the enforcement kit on, counts as another review round.

### Context Window Management

The context window is finite. Protect it:

- **Read selectively.** Use `offset`/`limit` on large files instead of reading the entire file. Read the section you need.
- **Don't re-read files** you already have in context unless they were modified since your last read.
- **Summarize at boundaries.** When a task spans many steps, summarize completed work before continuing — this is cheaper than re-reading everything.
- **Prefer Grep/Glob over exploratory reads.** Find the exact file:line first, then read a narrow range.
- **Don't load append-only logs** (session transcripts, build logs) into context unless explicitly asked.

#### Optimization Target: Tokens-per-Task, Not Tokens-per-Request

The correct metric is **tokens-per-task** — total tokens consumed from task start to completion, including re-fetching costs. Aggressive compression that loses a file path or decision forces the agent to re-read files and re-explore approaches, wasting more tokens than were saved. When deciding what to compress, preserve file paths, function names, error messages, and decisions — these are the most expensive to re-fetch.

#### Degradation Threshold

Degradation starts well before the context limit, whatever the window size. **Begin active compression at ~70–80% of the window.** Signs of onset: repeating earlier steps, forgetting which files were modified, losing track of decisions made.

Known degradation patterns to watch for:
- **Lost-in-middle**: Information in the center of context gets ~10–40% lower recall than content at the start or end. Place critical constraints and the current task at the top; put supporting detail in the middle.
- **Context poisoning**: A hallucination or wrong output that enters context gets reinforced on every subsequent turn. If outputs start diverging from what was agreed, treat context as potentially poisoned — summarize from scratch using only verified information.
- **Context distraction**: Irrelevant files or tool outputs in context reduce performance even if they're clearly not relevant. Even a single irrelevant document degrades recall. Trim aggressively.

#### Structured Summary Template (use before `/compact` or at ~70–80% of the window)

Structure forces preservation — each section is a checklist the summarizer must populate, preventing silent loss of file paths or decisions.

```markdown
## Session Intent
[What the user is trying to accomplish — one sentence]

## Files Modified
- [file path]: [what changed and why]
- [file path]: [what changed and why]

## Decisions Made
- [decision]: [reason]
- [decision]: [reason]

## Current State
- [tests: N passing, N failing]
- [what is working, what is not]

## Next Steps
1. [immediate next action]
2. [follow-on action]
```

**When to use:** Before `/compact`, before handing off to a sub-agent, or at ~70–80% of the window in a multi-step session. Automatic compaction makes manual compression rarely needed, but when it is triggered this template ensures the right information survives. Everything not in these sections can be lost.

### When to Break Tasks vs Do In-Session

```
Can I finish this in one session without losing context?
    |
    +-- YES (< ~15 files touched, clear scope) -> Do it yourself
    |
    +-- NO -> Break into subtasks:
        +-- Independent subtasks? -> Dispatch parallel background agents
        +-- Sequential subtasks? -> Complete each, summarize, continue
        +-- Too large even for subtasks? -> Stop. Ask human to scope down.
```

## Large Task Management

When a task is too large for a single context window:

- Break into self-contained subtasks with clear inputs/outputs
- Complete and verify each subtask before moving to the next
- Summarize completed work at each boundary for context carry-forward
- If losing track of earlier decisions, say so and request a recap

## Sub-Agent Governance

Sub-agents (via the Agent tool or Agent Teams) are powerful but have blind spots. Govern them.

### When to Use Sub-Agents vs Do It Yourself

| Situation | Action |
|-----------|--------|
| Single-file change, clear requirement | Do it yourself |
| Multi-file change within one domain | Do it yourself |
| 3+ tasks with an approved plan file | Use SDD pipeline (`subagent-driven-development` skill) |
| Parallel independent work streams | Use Agent Teams (TeamCreate) |
| Specialized review (security, DB, a11y) | Dispatch reviewer agent |

**Default:** Do it yourself. Sub-agents add coordination overhead — only use when parallelism or specialization justifies it.

### Mandatory Pre-Dispatch Checklist

Before dispatching ANY agent (Agent tool or TeamCreate):

1. **Plan-driven implementation → load `subagent-driven-development` first.** It defines the Implementer -> Spec Reviewer -> Quality Reviewer pipeline; skipping it skips review stages. A single reviewer or research dispatch does not need it.
2. **Pass explicit context.** A subagent starts in a fresh context: it never receives the conversation history or tool results. Custom and general-purpose subagents load the `CLAUDE.md` hierarchy (which includes `.claude/rules/`, so `lessons.md` too) unless their definition sets `omitClaudeMd`; the built-in Explore and Plan subagents do not. For the Agent tool: include the task, file paths and decisions in the `prompt` param (and any rules an Explore/Plan agent needs). For Teams: include in the initial `SendMessage` body.
3. **Specify the subagent_type.** Match the agent to the work — read-only agents (Explore, Plan) cannot edit files. Do not assign implementation to research agents.
4. **Set isolation when needed.** Use `isolation: "worktree"` for changes that might conflict with concurrent work.

### Mode-Specific Rules

| Concern | Task Tool (sub-agent) | Agent Teams (TeamCreate) |
|---------|----------------------|--------------------------|
| Context delivery | `prompt` parameter | `SendMessage` body — never say "read the plan" |
| Coordination | You manage sequentially | Shared `TaskList` + `SendMessage` between teammates |
| Task assignment | One task per dispatch | `TaskUpdate` with `owner` field |
| Shutdown | Agent returns automatically | You MUST send `shutdown_request` to each teammate, then `TeamDelete` |
| Idle teammates | N/A | Normal — idle means waiting for input, not broken. Send a message to wake them |

### Limitations (Both Modes)

- Explore and Plan subagents (and any agent with `omitClaudeMd`) start without `CLAUDE.md` and `.claude/rules/`; paste the relevant rules into the prompt or message. Other subagents inherit them
- Agent memory (native `memory:` frontmatter, v2.1.33): an agent that declares it **does** reliably re-read the first 200 lines of its OWN `.claude/agent-memory/<agent>/MEMORY.md` on each invocation — it just never reads another agent's memory, and overflow topic files load only on demand. So don't treat a `memory:`-enabled agent's notes as unread "orphans"; durable, cross-cutting knowledge still flows into `lessons.md`/skills via `/promote-lessons` (the review-gated path), not raw committed memory.
- Agents do not see prior conversation context unless the agent type description says "access to current context"
- Agent output is not visible to the user — you must summarize results back
- Team teammates cannot hear you unless you use `SendMessage` — plain text output is invisible to them

### Orphan Prevention

After any session using sub-agents or teams:

1. Check for `.claude/agent-memory/` files
2. Consolidate useful findings into `lessons.md` or skill reference files
3. Delete the orphaned files

This is automated by the `/promote-lessons` command and the stop hook reminder.
