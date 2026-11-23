---
name: audit-skills
description: Periodic health audit of all skills in .claude/skills/ and agents in .claude/agents/. Scores each against a 16-criterion rubric (32 points max), assigns A–F production readiness grade (80% = B = production ready), and outputs a prioritised fix list. Use when: auditing skill health, reviewing skill governance, finding stale skills, checking skill compliance, grading the skill library.
allowed-tools: Read, Glob, Grep, Bash
---

Audit all skills in `.claude/skills/` and agents in `.claude/agents/`. Score each against the 16-criterion rubric below. Output a graded report with prioritised fixes.

## Scoring Rubric (16 criteria × 2 points = 32 points max)

Each criterion scores **0** (fail), **1** (partial), or **2** (pass).

### Category A — Iron Law & Trigger (8 pts)

| # | Criterion | 2 (pass) | 1 (partial) | 0 (fail) |
|---|-----------|----------|-------------|----------|
| A1 | **Iron Law present** | `## Iron Law`, `**Iron Law:**`, or `> **Iron Law:**` found in body | Mandatory action present but not labelled Iron Law | Absent |
| A2 | **Description has CSO trigger words** | Contains specific trigger verbs: "Use when", "Triggers when", "Invoke for" + concrete scenario | Has trigger words but vague ("use for general...") | Missing or < 10 words |
| A3 | **Trigger is unambiguous** | Would NOT fire on tasks outside its domain | Could plausibly fire on 2+ unrelated task types | Fires on everything / too broad |
| A4 | **No overlap with peer skills** | No functional duplication with another skill in `.claude/skills/` | Minor overlap, clearly differentiated | Significant duplication — consolidate |

### Category B — Structure & Size (8 pts)

| # | Criterion | 2 (pass) | 1 (partial) | 0 (fail) |
|---|-----------|----------|-------------|----------|
| B1 | **Frontmatter complete** | `name`, `description`, `allowed-tools` all present | 2 of 3 present | Missing or malformed frontmatter |
| B2 | **Body ≤ 500 lines** | ≤ 450 lines | 451–500 lines | > 500 lines |
| B3 | **Progressive disclosure** | Content ordered: summary → key rules → examples → reference | Mostly ordered, minor issues | Dumps everything upfront with no structure |
| B4 | **References section** | `references/` dir present OR inline links to MCP/docs | Referenced in body but dir missing | No references anywhere |

### Category C — Content Quality (8 pts)

| # | Criterion | 2 (pass) | 1 (partial) | 0 (fail) |
|---|-----------|----------|-------------|----------|
| C1 | **MCP server named explicitly** | Specific MCP server listed (e.g. `dart-mcp-server`, `context7`, `angular-cli`) | Generic "use MCP" without naming which | No MCP reference for a tech that has one |
| C2 | **Code examples present** | ≥ 1 concrete code block showing correct usage | Examples described in prose only | No examples |
| C3 | **Anti-patterns documented** | ≥ 1 explicit "don't do this" section or callout | Anti-patterns implied but not explicit | Absent |
| C4 | **Stack version pinned** | Specific version referenced (e.g. "NestJS 11.x", "Flutter 3.41.x") | Stack named without version | No stack version |

### Category D — Safety & Ops (8 pts)

| # | Criterion | 2 (pass) | 1 (partial) | 0 (fail) |
|---|-----------|----------|-------------|----------|
| D1 | **allowed-tools declared and minimal** | Tools listed AND scoped to only what's needed | Tools listed but overly broad (`*` or all tools) | Missing |
| D2 | **No forbidden files referenced** | Does not reference `.env`, `secrets`, CI/CD config, or prod infra | References mentioned but with clear warnings | Directly references forbidden files without caveat |
| D3 | **Error handling pattern shown** | Explicit error/failure path shown in examples | Error handling mentioned in prose | Absent — only happy path shown |
| D4 | **Verify/test step included** | "Run X to verify" step present | Verification implied | No verification step |

---

## Grade Scale

```
A  90–100%  (29–32 pts)  Production-ready. No action needed.
B  80–89%   (26–28 pts)  Good. Minor polish only.
C  70–79%   (22–25 pts)  Functional but gaps. Fix before relying on it.
D  60–69%   (19–21 pts)  Risky. Missing key pieces.
F  < 60%    (< 19 pts)   Do not use. Rewrite or delete.
```

**Production-ready threshold: 80% (B grade, ≥ 26 points)**

---

## Staleness Rule

Today's date: use `currentDate` from context if available, otherwise run `date +%Y-%m-%d`.

- `last-reviewed` missing or > 180 days ago → criterion A1 capped at 1 (cannot be 2 regardless of content)
- `last-reviewed` 91–180 days ago → note as WARN in report but no score penalty
- `last-reviewed` ≤ 90 days ago → no staleness impact

---

## Steps

1. Run `glob .claude/skills/*/SKILL.md` — get all skill files
2. Run `glob .claude/agents/*.md` — get all agent files
3. For each file:
   a. Read frontmatter + full body (use `limit: 60` first, expand if needed)
   b. Score all 16 criteria (0/1/2 each)
   c. Sum score, compute percentage, assign grade
4. Sort results: F first, then D, C, B, A
5. **Permissions and automation surface re-audit** (every run, and at least every 30 days): permissions accrete and are never re-examined, so re-check `.claude/settings.json` and `.claude/settings.local.json` against `.claude/skills/security-reviewer/reference/claude-config-security.md` §1 (permissions), §3 (hooks), §4 (MCP servers) and §5 (agents), deriving the current state with its §6 commands:
   - every `permissions.allow` entry is attributable to a current workflow; unattributable entries are candidates for removal or demotion to `ask`
   - destructive classes (`rm`, `git reset/clean/restore`, force-push, `sudo`, `eval`, `ssh`) are still in `ask` or `deny`, none silently promoted to `allow`
   - every allow entry added since the last audit (`git log -p -- .claude/settings.json`) has a stated reason
   - every registered hook file exists and is executable (an orphaned hook entry is a silent enforcement gap)
   - every `mcp__*` allow entry maps to a server still in `.mcp.json` and still listed as reviewed in `.claude/rules/skill-triggers.md`
   Report this as its own section: PASS, or each flagged entry with its reason.
6. Output report in format below

---

## Report Format

```
# Skill & Agent Audit Report — {DATE}
═══════════════════════════════════════════════════════

SKILLS:  {N} audited  |  A: {N}  B: {N}  C: {N}  D: {N}  F: {N}
AGENTS:  {N} audited  |  A: {N}  B: {N}  C: {N}  D: {N}  F: {N}

Production-ready (A+B): {N}/{TOTAL} ({PCT}%)
Needs work (C+D+F):     {N}/{TOTAL} ({PCT}%)

## ❌ F Grade — Do Not Use (rewrite or delete)
| Name | Score | Top 3 Missing |
|------|-------|---------------|
| skill-name | 14/32 (44%) F | Iron Law, MCP server, error handling |

## ⚠️ D Grade — Risky (fix before relying on)
| Name | Score | Top 3 Missing |
|------|-------|---------------|
| skill-name | 21/32 (66%) D | Anti-patterns, references, version pin |

## 🔧 C Grade — Functional with gaps
| Name | Score | Quick Wins |
|------|-------|-----------|
| skill-name | 24/32 (75%) C | Add REFERENCES.md (+2→B), add anti-patterns (+2→A) |

## ✅ B Grade — Production Ready (minor polish)
{skill-name} 27pts, {skill-name} 26pts, ...

## 🏆 A Grade — Exemplary
{skill-name} 31pts, {skill-name} 30pts, ...

---

## Priority Fix List (sorted by ROI — biggest score gain per fix)

1. [{skill}] Add REFERENCES.md with MCP links — +2pts → grade {X→Y}
2. [{skill}] Add anti-patterns section — +2pts → grade {X→Y}
3. [{skill}] Pin stack version in frontmatter — +1pt
...

## Summary
- Most common failure: {criterion name} (missing in {N} skills)
- Fastest library-wide improvement: {action} (+{N} total points across {N} skills)
```

---

## Rules

- Score every criterion independently — do NOT adjust scores based on overall impression
- Show the specific file:line evidence for each 0 score in the full detail view
- For C-grade skills: always show the 2 cheapest fixes that would move them to B
- Do NOT auto-fix anything — report only, human decides
- If total library production-readiness (A+B %) < 50% — flag this prominently at the top
