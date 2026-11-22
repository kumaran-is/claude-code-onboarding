# Giskard OSS v3 Patterns (`giskard.checks`)

> API checked against the giskard-oss `giskard-checks` README via Context7 (`/giskard-ai/giskard-oss`) on 2026-11-22; Giskard was **not** installed or executed here. Re-query Context7 before writing code.
> **v3 only**: v2 APIs (`giskard.scan`, `giskard.rag` RAGET, `generate_testset`, `KnowledgeBase`) are legacy and not used.

## Install

```toml
# pyproject.toml (eval dependency group)
giskard-checks = "==<pinned>"   # pin the exact version you verified via Context7
```

## Judge configuration

```python
import os
from giskard.checks import set_default_generator

# Accepts a BaseGenerator instance or a "provider/model" identifier string (LiteLLM-style).
# The library default is an OpenAI model: set it once per session (conftest), from config.
set_default_generator(os.environ["EVAL_JUDGE_LITELLM_ID"])
```

## Scenario: one interaction, several checks

```python
from giskard.checks import Groundedness, Scenario

scenario = (
    Scenario("grounded_answer")
    .interact(inputs=question, outputs=call_agent)          # outputs: static value or callable(inputs)
    .check(Groundedness(name="answer is grounded",
                        target_key="trace.last.outputs",     # NOT answer_key
                        context=retrieved_chunks))
)
result = await scenario.run()          # scripts without an event loop: scenario.run_sync()
assert result.passed
```

## Suite: many scenarios, one target

```python
from giskard.checks import Equals, Scenario, Suite

suite = Suite(name="support_answer_security", target=call_agent)
suite.append(prompt_injection_scenario)      # append, not add
suite.append(cross_tenant_scenario)
results = await suite.run()
if results.pass_rate is None:                # nothing was evaluated (empty or fully skipped)
    raise RuntimeError("Giskard suite evaluated zero scenarios: NOT RUN, not PASS")
```

Persist per-scenario results yourself (JSON rows with case id, judge id, check name, passed). Check the pinned version's docs before relying on any built-in report exporter.

## Deterministic checks: test them against the compliant answer too

- A string/regex check must be run against the expected refusal or compliant output as a negative control; a topic ban (`Not(RegexMatching("<policy topic>"))`) also matches the correct refusal that names the topic. Shape prohibitions around the violating claim ("you are entitled to ...", "done"), not topic words.
- Do not treat a regex over reply text (for example "no `tenant_id:` in the answer") as an isolation test. Isolation is asserted on tool arguments, retrieval results and persisted rows (`golden-dataset.md` "Isolation, memory and side effects").
- Exact-value assertions (an enum label, a status) are cheaper and stricter as plain Python on the structured output than as an LLM check.

## Known Gotchas

| Gotcha | Fix |
|--------|-----|
| `answer_key=` on checks | `target_key="trace.last.outputs"` |
| `suite.add(...)` | `suite.append(...)` |
| `Generator(model=...)` from `giskard.agents` | `set_default_generator("<provider/model>")` from `giskard.checks` |
| `pass_rate is None` treated as success | It means nothing ran: NOT RUN |
| v2 imports (`giskard.rag`, `giskard.scan`) | Use `giskard.checks` only |
| Async tests | `asyncio_mode = "auto"`; see `pytest-harness.md` |
