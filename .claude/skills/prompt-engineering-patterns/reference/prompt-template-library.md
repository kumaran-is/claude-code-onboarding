# Prompt Template Library — Index

> 15 copy-paste starting templates, each with a LangGraph (`SystemMessage`) and a Google ADK (`LlmAgent`) version, split by what consumes the output. Template mechanics (registries, factories, multi-turn): `prompt-templates.md`. System prompt structure: `system-prompts.md`.

| Output consumed by | File | Templates |
|---|---|---|
| Code (schema-enforced) | `prompt-library-structured-output.md` | Code Review, Multi-Class Classification, Data Extraction, Sentiment Analysis, Schema Validation Explainer, Prompt Injection Detector |
| Code or a grounded reader | `prompt-library-code-and-grounding.md` | SQL Generation, RAG Answer, Test Generation, Error Analysis |
| A person | `prompt-library-writing-and-advisory.md` | Summarization, API Documentation, Decision Maker, Code Refactor Advisor, Release Notes Generator |

Rules every template follows:

- Code that reads fields gets a Pydantic schema (`with_structured_output` / ADK `output_schema`) with validation and one bounded retry, never "output JSON" in prompt text plus `json.loads`.
- Untrusted input (user text, documents, code, tool output) goes in the user turn inside tags, marked as data.
- Business rules and security boundaries are enforced in code, not by prompt wording.
