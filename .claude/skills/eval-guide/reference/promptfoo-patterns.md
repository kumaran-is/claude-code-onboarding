# Promptfoo Patterns

> **Verify via Context7 (`promptfoo`) before using.** These patterns reflect API state as of 2026-04-28.

## Install

```bash
# MCP server / Node.js tooling
npm install --save-dev promptfoo   # pin to latest stable after Context7 verification
# OR: npx promptfoo eval (zero-install)
```

## Provider Configuration

```yaml
# tests/eval/promptfoo/shared-provider.yaml
providers:
  - id: google:gemini-2.5-pro        # confirmed provider format for Gemini stacks
    # alt: vertex:gemini-2.5-pro     # use when Vertex AI auth preferred over API key
    # alt: openai:gpt-4o             # use for OpenAI stacks
    config:
      temperature: 0.0               # deterministic for eval runs
# Best practice: use the same LLM provider as your main stack for consistency
```

## Key Assertion Types

| Assertion type | What it checks | Example use |
|----------------|---------------|-------------------|
| `equals` | Exact match | `label == "urgent"` in a classifier output |
| `contains` / `icontains` | Substring (case-insensitive) | Response contains "contact support" |
| `not-contains` | Substring absent | No cross-tenant ID in output |
| `regex` | Pattern match | Phone/email redaction validation |
| `llm-rubric` | LLM grades using free-text rubric | "Does response follow your policy?" |
| `model-graded-closedqa` | Closed Q&A grading (yes/no) | "Is answer grounded in source document?" |
| `factuality` | Factual consistency vs reference | QA agent answer vs known ground truth |
| `is-json` / `contains-json` | Output is valid JSON | Structured ADK output schemas |
| `javascript` | Arbitrary JS assertion | Custom multi-field validation |
| `python` | Arbitrary Python assertion | Call your policy detector |
| `similar` | Embedding cosine similarity ≥ threshold | Match rationale similarity |
| `is-valid-openai-tools-call` | MCP/function-call schema validation | MCP tool call JSON matches declared schema |
| `function-call-count` | Number of tool calls | Guard against excessive-agency patterns |
| `cost` | Token cost ≤ threshold | Cost regression gate per agent |
| `latency` | Response time ≤ ms threshold | SLA enforcement |

## Classifier Regression Suite Template (live model: R2, not R1)

```yaml
# tests/eval/promptfoo/classifier.yaml
description: "your_agent regression suite"
providers:
  - id: google:gemini-2.5-pro
    config:
      temperature: 0.0

prompts:
  - file://prompts/classify/system.txt

defaultTest:
  assert:
    - type: latency
      threshold: 2000   # adjust to your SLA

tests:
  - description: "critical classification — high-priority input"
    vars:
      input: "Your domain-specific critical input here"
    assert:
      - type: icontains
        value: "Critical"
      - type: llm-rubric
        value: "Response classifies as critical priority and recommends immediate action"

  - description: "low priority — routine issue"
    vars:
      input: "Your domain-specific low-priority input here"
    assert:
      - type: icontains
        value: "Low"
      - type: not-contains
        value: "Critical"

  - description: "policy compliance — restricted criteria must be flagged"
    vars:
      input: "Input that should trigger your policy detector"
    assert:
      - type: python
        value: |
          # Your policy detector must have flagged this
          import json
          output = json.loads(output)
          return output.get("review_required") == True
```

## Red-Team Suite Template

```yaml
# tests/eval/promptfoo/redteam-your-agent.yaml
description: "your_agent red-team suite"
providers:
  - id: google:gemini-2.5-pro
    config:
      temperature: 0.0

targets:
  - id: python:tests/eval/promptfoo/adapters/your_agent_adapter.py

redteam:
  purpose: >
    Describe your agent's purpose and key constraints here.
    Must not reveal other tenants' data or violate domain policies.
  numTests: 25
  plugins:
    - prompt-injection
    - bola                          # cross-tenant data access (CI BLOCKER #1)
    - excessive-agency
    - harmful:privacy
    - rag-poisoning
    - cross-session-leak
    - id: policy
      config:
        policy: >
          Describe your project's policy constraints here.
          The agent must not disclose other tenants' data.
          Restricted criteria must never appear in agent-generated output.
  strategies:
    - basic
    - jailbreak
    - crescendo                     # multi-turn escalation attack
    - goat                          # goal hijacking via persistence
```

## MCP Security Suite Template

```yaml
# tests/eval/promptfoo/mcp-security.yaml
providers:
  - type: mcp
    config:
      serverPath: mcp/your-project-mcp/
      env:
        DATABASE_URL: ${DATABASE_URL}

tests:
  - description: "search tool returns valid tool call"
    vars:
      input: "Find resources matching criteria"
    assert:
      - type: is-valid-openai-tools-call
      - type: function-call-count
        max: 1                          # excessive-agency guard
      - type: not-contains
        value: "tenant_id:"             # no cross-tenant IDs in response (CI BLOCKER #4)
```

## 70+ Red-Team Plugins Reference

| Plugin | What it tests | CI blocker # |
|--------|-------------|-------------|
| `prompt-injection` | Direct/indirect prompt injection | #2 |
| `bola` | Cross-tenant data access | #1 |
| `bfla` | Broken function level authorization | — |
| `rbac` | Role-based access violations | — |
| `excessive-agency` | Agent takes unauthorized actions | — |
| `mcp` | MCP tool-poisoning, unauthorized discovery | #4, #5 |
| `rag-poisoning` | Adversarial content in retrieved docs | — |
| `rag-document-exfiltration` | Extracting raw retrieval corpus | #6 |
| `cross-session-leak` | Session A data leaks into session B | #1 |
| `agentic:memory-poisoning` | Poisoning agent memory/state | — |
| `bias` | Discriminatory model behavior | — |
| `harmful:privacy` | PII extraction / privacy violations | — |
| `pii` / `pii:direct` | PII leakage in output | — |
| `owasp:llm:01` | LLM01 — Prompt injection | #2 |
| `owasp:llm:06` | LLM06 — Sensitive info disclosure | — |
| `owasp:llm:08` | LLM08 — Excessive agency | — |
| `id: policy` | Custom domain policy rules | #3 |

Full list of 70+ plugins: verify via Context7 (`promptfoo`).

## CI Integration

```bash
# Promptfoo calls a live model (and llm-rubric calls a judge): R2+ only. R1 stays deterministic (pytest).
# Tier R2 — Nightly (regression + red-team suites)
npx promptfoo eval -c tests/eval/promptfoo/classifier.yaml
npx promptfoo eval -c tests/eval/promptfoo/ --fail-on-error --output results/promptfoo-r2.json

# Parse results
npx promptfoo view results/promptfoo-r2.json
```

## Known Gotchas

| Gotcha | Fix |
|--------|-----|
| `google:gemini-2.5-pro` vs `vertex:gemini-2.5-pro` | Both confirmed; use `google:` for API key auth, `vertex:` for Workload Identity on GCP |
| `jailbreak` keyword in issue bodies blocked by pre-commit hook | Use "adversarial bypass" or "instruction override" in GitHub issue text |
| Promptfoo exit code 0 on assertion failure | Always check `results.json` stats, not just exit code |
| `python:` assertion type needs adapter file | Create `tests/eval/promptfoo/adapters/<agent>_adapter.py` per agent |
