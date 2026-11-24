# MCP Server Evaluation -- Criteria and Question Design

## Overview

This document provides guidance on creating comprehensive evaluations for MCP servers. Evaluations test whether LLMs can effectively use your MCP server to answer realistic, complex questions using only the tools provided.

### Evaluation Requirements
- Create 10 human-readable questions
- Questions must be READ-ONLY, INDEPENDENT, NON-DESTRUCTIVE
- Each question requires multiple tool calls (potentially dozens)
- Answers must be single, verifiable values
- Answers must be STABLE (won't change over time)

### Output Format
```xml
<evaluation>
   <qa_pair>
      <question>Your question here</question>
      <answer>Single verifiable answer</answer>
   </qa_pair>
</evaluation>
```

---

## Purpose of Evaluations

The measure of quality of an MCP server is NOT how well or comprehensively the server implements tools, but how well these implementations (input/output schemas, docstrings/descriptions, functionality) enable LLMs with no other context and access ONLY to the MCP servers to answer realistic and difficult questions.

## Question Guidelines

### Core Requirements

1. **Questions MUST be independent** -- should NOT depend on answers to other questions
2. **Questions MUST require ONLY NON-DESTRUCTIVE AND IDEMPOTENT tool use**
3. **Questions must be REALISTIC, CLEAR, CONCISE, and COMPLEX** -- require multiple tools or steps

### Complexity and Depth

4. **Require deep exploration** -- multi-hop questions requiring sequential tool calls
5. **May require extensive paging** -- querying old data (1-2 years) to find niche information
6. **Require deep understanding** -- may use True/False or multiple-choice formats requiring evidence
7. **Must not be solvable with straightforward keyword search** -- use synonyms, related concepts, or paraphrases

### Tool Testing

8. **Stress-test tool return values** -- large JSON objects, multiple data modalities (IDs, timestamps, URLs, file names)
9. **Reflect real human use cases** -- information retrieval tasks humans would care about
10. **May require dozens of tool calls** -- challenges LLMs with limited context
11. **Include ambiguous questions** -- force difficult decisions while still having a single verifiable answer

### Stability

12. **Answers MUST NOT CHANGE** -- avoid dynamic state (reaction counts, member counts, open issue counts)
13. **DO NOT let the MCP server RESTRICT the kinds of questions** -- create challenging questions even if some may not be solvable

## Answer Guidelines

### Verification
- Answers must be VERIFIABLE via direct string comparison
- Specify output format in the question: "Use YYYY/MM/DD.", "Respond True or False."
- Answer should be a single value: user ID, channel name, timestamp, boolean, email, URL, numerical quantity, multiple choice

### Readability
- Prefer HUMAN-READABLE formats (names, dates, URLs) over opaque IDs
- The vast majority of answers should be human-readable

### Stability
- Base questions on "closed" concepts (ended conversations, completed projects, launched features)
- Use fixed time windows to insulate from non-stationary answers

### Diversity
- Answers should span diverse modalities: user names, channel IDs, message strings, timestamps, emails, booleans
- Answers must NOT be complex structures (lists, objects) unless straightforwardly verifiable by string comparison

## Evaluation Process

### Step 1: Documentation Inspection
Read the target API documentation. Parallelize as much as possible.

### Step 2: Tool Inspection
List available MCP server tools. Understand schemas, descriptions. Do NOT call tools yet.

### Step 3: Developing Understanding
Iterate steps 1-2. Do NOT read the MCP server implementation code itself.

### Step 4: Read-Only Content Inspection
USE the MCP server tools with READ-ONLY operations to identify specific content for realistic questions. Make INCREMENTAL, SMALL, TARGETED tool calls. Use `limit` parameter (<10). Use pagination.

### Step 5: Task Generation
Create 10 human-readable questions following all guidelines above.

## Evaluation Examples

### Good Questions

**Multi-hop (GitHub MCP):**
```xml
<qa_pair>
   <question>Find the repository archived in Q3 2023 that had previously been the most forked in the org. What was the primary programming language?</question>
   <answer>Python</answer>
</qa_pair>
```
Good: requires multiple searches, examining details, stable historical data.

**Context without keyword matching (Project Management MCP):**
```xml
<qa_pair>
   <question>Locate the initiative focused on improving customer onboarding completed in late 2023. The project lead created a retrospective. What was the lead's role title?</question>
   <answer>Product Manager</answer>
</qa_pair>
```
Good: no specific project name, requires finding and cross-referencing data.

**Complex aggregation (Issue Tracker MCP):**
```xml
<qa_pair>
   <question>Among critical bugs reported in January 2024, which assignee resolved the highest percentage within 48 hours? Provide their username.</question>
   <answer>alex_eng</answer>
</qa_pair>
```
Good: filtering, grouping, calculating rates, understanding timestamps.

### Poor Questions

- **Answer changes over time**: "How many open issues?" -- dynamic state
- **Too easy**: Searching for an exact title -- straightforward keyword search
- **Ambiguous answer format**: "List all repositories with Python" -- list ordering varies

## Verification Process

After creating evaluations:
1. Examine the XML file
2. Load each task and solve it yourself using the MCP server tools (in parallel)
3. Flag any operations requiring WRITE or DESTRUCTIVE operations
4. Replace incorrect answers
5. Remove any qa_pairs requiring destructive operations

## Tips

1. Think hard and plan ahead before generating tasks
2. Parallelize where opportunity arises
3. Focus on realistic use cases
4. Create challenging questions that test limits
5. Ensure stability by using historical data
6. Verify answers by solving questions yourself
7. Iterate and refine

---

## Agent Behavior Metrics (DeepEval)

The QA-pair evaluation above tests whether agents *find the right answer*. Agent behavior metrics test whether agents *use your MCP server correctly* — right tools, right arguments, completed workflows. Use both together for production readiness.

### The Three Core Metrics

| Metric | What It Measures | Range |
|--------|-----------------|-------|
| **Primitive Usage Score** | Did the agent call the right tools? | 0.0 – 1.0 |
| **Argument Correctness Score** | Did the agent pass the right arguments? | 0.0 – 1.0 |
| **Task Completion Score** | Did the agent accomplish the actual goal? | 0.0 – 1.0 |

**Production threshold:** All three must score ≥ 0.7 before shipping. Use 0.5 for permissive (early dev), 0.9 for high-stakes (payment, deletion, healthcare).

**Minimum-within rule:** `MCPUseMetric` score = `min(primitive_usage, argument_correctness)`. A tool called with wrong arguments scores as badly as calling the wrong tool — both indicate the MCP server interface is unclear.

### Low Score Root Cause Diagnosis

| Score | Likely Cause | Fix |
|-------|-------------|-----|
| Low primitive usage | Ambiguous tool descriptions — agent can't distinguish tools | Rewrite tool `description` to start with the specific action verb |
| Low argument correctness | Unclear parameter schemas — agent guesses field names or types | Add `.describe()` to every `z.string()` field; include format examples |
| Low task completion | Underspecified task flow — agent doesn't know what "done" looks like | Add `next_actions` directives (Pattern 1) to guide workflow completion |

### Implementation (Python / DeepEval)

```python
from deepeval import evaluate
from deepeval.test_case import LLMTestCase, ConversationalTestCase, Turn
from deepeval.metrics import MCPUseMetric, MCPTaskCompletionMetric

# Single-turn evaluation
def test_product_search_tool_use():
    test_case = LLMTestCase(
        input="Find waterproof boots under $150 for customer 42",
        actual_output=agent_response,
        tools_called=agent_tool_calls,          # list of {name, args} dicts
        expected_tools=[
            {"name": "search_products", "args": {"query": "waterproof boots", "max_price": 150, "customer_id": "42"}}
        ]
    )
    metric = MCPUseMetric(threshold=0.7)
    metric.measure(test_case)
    assert metric.score >= 0.7, f"MCPUse score {metric.score}: {metric.reason}"

# Multi-turn (ConversationalTestCase) — for stateful workflows
def test_checkout_workflow():
    test_case = ConversationalTestCase(
        turns=[
            Turn(
                input="I want to order the waterproof boots for customer 42",
                actual_output=agent_turn_1_response,
                tools_called=turn_1_tool_calls
            ),
            Turn(
                input="Deliver them next Tuesday",
                actual_output=agent_turn_2_response,
                tools_called=turn_2_tool_calls
            ),
            Turn(
                input="Confirm the order",
                actual_output=agent_turn_3_response,
                tools_called=turn_3_tool_calls
            )
        ]
    )
    completion_metric = MCPTaskCompletionMetric(threshold=0.7)
    completion_metric.measure(test_case)
    assert completion_metric.score >= 0.7
```

### Edge Case Test Categories

Every MCP server eval suite must include these four edge case categories:

| Category | Example | Why It Matters |
|----------|---------|----------------|
| **Abbreviations** | "PO" instead of "purchase order" | Agent must map informal language to correct tool params |
| **Disambiguation** | "Cancel it" — the order or the subscription? | Agent must ask or infer from context rather than guessing |
| **Implicit context** | "Same address as last time" in multi-turn | Agent must carry forward session context correctly |
| **Format preferences** | "Next Friday" instead of ISO date | Agent must normalize before passing to tools |

### Eval Suite Structure

```python
# Minimum viable eval suite for any MCP server
eval_cases = [
    # Happy path — basic tool calls work
    happy_path_case,
    # Edge cases — all 4 categories above
    abbreviation_case,
    disambiguation_case,
    implicit_context_case,
    format_preference_case,
    # Error recovery — agent handles tool errors
    error_recovery_case,
    # Multi-step workflow — task completion
    workflow_case,
]

results = evaluate(eval_cases, metrics=[
    MCPUseMetric(threshold=0.7),
    MCPTaskCompletionMetric(threshold=0.7)
])
```

**Minimum bar:** 7 test cases (3 happy path + 4 edge case categories). Add workflow tests when your server supports multi-step operations.

## Deterministic Gate Before LLM Evals (TypeScript servers)

LLM evals are slow and probabilistic; run them only after the deterministic layer is green. Verified 2026-11-23 against Node 26.13.1, TypeScript 6.0.3, vitest 5.1.1, @vitest/coverage-v8 5.1.1, eslint 10.15.0, typescript-eslint 8.74.0 and prettier 3.10.1 (every row also failed on a planted violation: see [production-deployment-docker.md](production-deployment-docker.md) §0).

```typescript
// vitest.config.ts: tests call the server through a real @modelcontextprotocol/client Client (no mocked transport)
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    environment: 'node',
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['src/stdio.ts', 'src/http.ts'], // process entry points: covered by the /verify MCP block and the image smoke test
      reporter: ['text', 'json-summary'],
      thresholds: { lines: 80, functions: 80, branches: 70, statements: 80 },
    },
  },
});
```

```javascript
// eslint.config.js (flat config)
// @ts-check
import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import { defineConfig } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig(
  { ignores: ['dist/', 'coverage/'] },
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      globals: globals.node,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      'no-console': 'error', // stdout belongs to the stdio transport; log with pino to stderr
      '@typescript-eslint/no-floating-promises': 'error',
    },
  },
  { files: ['**/*.js'], extends: [tseslint.configs.disableTypeChecked] },
  prettier,
);
```

- `vitest run` exits 0 when every test is skipped: gate on the executed count (`--reporter=json` + the count check in `node-ci-and-observability.md` §4, or `/verify full`, which fails "executed 0").
- Under `exactOptionalPropertyTypes: true`, passing Fastify's `req.raw` to `toNodeHandler` (`@modelcontextprotocol/node` 2.1.2) fails with TS2379 (`method?: string` vs `string | undefined`); leave the flag off or cast at that one call.
- Inspector 2.16.0 CLI as a scripted check (no browser): `npx -y @modelcontextprotocol/inspector@2.16.0 --cli node dist/stdio.js --method tools/call --tool-name <tool> --tool-arg key=value` exits 0 on success and 5 when the result has `isError: true` (`--method tools/list` lists tools). An ad-hoc command writes no catalog file; `--catalog` is rejected in that mode (it is for named `--server` entries).
