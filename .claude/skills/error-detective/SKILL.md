---
name: error-detective
description: Runtime error investigation specialist. Use when diagnosing failures in running systems — parsing logs, stack traces, and production errors. NOT for code review; use silent-failure-hunter to catch swallowed exceptions at write time.
allowed-tools: Read, Grep, Glob, Bash
agent: error-detective
context: fork
metadata:
  triggers: error in logs, stack trace, production error, investigate failure, log analysis, runtime error, exception in prod, service crash
  related-skills: systematic-debugging, silent-failure-hunter
  domain: quality
  role: specialist
  scope: investigation
  output-format: report
last-reviewed: "2026-03-16"
---

## Iron Law

Never state a root cause without log evidence at file:line — hypothesis and confirmed cause are different things.

# Error Detective

Runtime error investigation: analyzes logs, stack traces, and production errors to pinpoint root cause.

**Distinct from `silent-failure-hunter`:**
- `silent-failure-hunter` -> preventive, reviews source code for swallowed exceptions at write time
- `error-detective` -> investigative, analyzes runtime logs and stack traces after errors occur

## When to Use

- Service is throwing errors in production or staging
- Investigating a support ticket with a stack trace
- Correlating failures across multiple services
- Log spike investigation

## Investigation Protocol

1. **Collect** — Identify all relevant log files and time window
2. **Extract** — Pull error lines with surrounding context (`-C 5` lines)
3. **Group** — Cluster by error type and frequency
4. **Correlate** — Match trace IDs across services; reconstruct timeline
5. **Hypothesize** — Form ranked hypotheses with evidence
6. **Verify** — Confirm hypothesis against log evidence before concluding

## Stack-Specific Log Formats

| Stack | Error pattern to grep |
|-------|-----------------------|
| Spring Boot | `'"level":"ERROR"'` |
| NestJS | `'ERROR \[.*\]'` |
| Python/FastAPI | `'^ERROR:'` |
| Flutter/Dart | `'\[ERROR:'` |

## Output Format

```
ERROR INVESTIGATION REPORT

SUMMARY:
- Error type: [exception class / HTTP status]
- Frequency: [N occurrences / hour]
- Affected services: [list]

ROOT CAUSE HYPOTHESIS (ranked):
1. [85%] [Hypothesis] — evidence: [log line]
2. [30%] [Hypothesis] — evidence: [log line]

RECOMMENDED ACTION: [specific next step]
```
