---
name: weaviate-cookbooks
description: "Build complete AI applications with Weaviate — Query Agent chatbots, data explorers, multimodal PDF RAG, basic/advanced/agentic RAG pipelines, and DSPy tool-calling agents. Use when scaffolding a full-stack Weaviate application from scratch. Triggers: 'build a chatbot', 'RAG pipeline', 'Query Agent app', 'document search', 'data explorer', 'multimodal search', 'agentic RAG', 'Weaviate app'."
allowed-tools: Read, Glob, Grep
metadata:
  triggers: Query Agent, RAG pipeline, chatbot, Weaviate app, document search, data explorer, multimodal RAG, agentic RAG, DSPy agent
  related-skills: vector-database, weaviate, agentic-ai-dev, python-dev
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-03-15"
---

# Weaviate Cookbooks

## Iron Law

**READ `references/project_setup.md` AND `references/environment_requirements.md` BEFORE GENERATING ANY COOKBOOK CODE.**

Every cookbook shares connection management, dependency setup, and env var patterns. Skipping setup causes runtime failures that look like Weaviate bugs but are actually missing config.

## Quick Cookbook Selector

| Use Case | Cookbook | Complexity | Best For |
|----------|----------|-----------|----------|
| Ask questions, get answers | [Query Agent Chatbot](references/query_agent_chatbot.md) | Low | Q&A interfaces, conversational search |
| Browse and filter data | [Data Explorer](references/data_explorer.md) | Low | Exploratory analytics, dashboards |
| Search PDFs / documents | [Multimodal RAG](references/pdf_multimodal_rag.md) | Medium | Document retrieval, file search |
| Basic retrieval + generation | [Basic RAG](references/basic_rag.md) | Low | First RAG implementation |
| Production RAG + reranking | [Advanced RAG](references/advanced_rag.md) | High | Complex retrieval, multi-stage ranking |
| Tool-calling agent | [Basic Agent](references/basic_agent.md) | Medium | Structured task automation with DSPy |
| RAG + agents combined | [Agentic RAG](references/agentic_rag.md) | High | Multi-tool workflows, hierarchical retrieval |

## Process

1. **Read** `references/project_setup.md` — dependency management, venv, project layout
2. **Read** `references/environment_requirements.md` — all required env vars
3. **Select cookbook** from the table above based on use case
4. **Read** the target cookbook reference file fully before generating code
5. **Scaffold** — generate project structure, then fill in implementation
6. **(Optional)** Add frontend via `references/frontend_interface.md`
7. **(Optional)** Use async client for FastAPI via `references/async_client.md`

## Reference Files

| File | Content | When to Use |
|------|---------|-------------|
| `references/project_setup.md` | venv, dependencies, project layout, connection management | **Always — read first** |
| `references/environment_requirements.md` | All env vars, provider keys, `.env` template | **Always — read first** |
| `references/query_agent_chatbot.md` | FastAPI backend + streaming chat + chat history | Building Q&A chatbot |
| `references/data_explorer.md` | Sorting, keyword search, tabular UI | Building data browser |
| `references/pdf_multimodal_rag.md` | ModernVBERT + Ollama Qwen3-VL, PDF ingestion | PDF/document search |
| `references/basic_rag.md` | Retrieval + generation, simple pipeline | First RAG implementation |
| `references/advanced_rag.md` | Reranking, query decomposition, LLM filter selection | Production RAG |
| `references/basic_agent.md` | DSPy AgentResponse, RouterAgent, tool design | Tool-calling agents |
| `references/agentic_rag.md` | RAG tools, LLM filters, vector DB memory, Query Agent | Agentic RAG systems |
| `references/frontend_interface.md` | Next.js frontend for Weaviate backend | Adding a UI layer |
| `references/async_client.md` | Async client, FastAPI lifecycle, multi-cluster | Production async apps |

## Documentation Sources

Before generating code, consult these sources:

| Source | Tool | Purpose |
|--------|------|---------|
| Weaviate Python v4 | `weaviate-docs` MCP | Collection APIs, query patterns, async client |
| Weaviate general docs | `weaviate-docs` MCP | Application architecture, best practices |
| FastAPI | `Context7` MCP | Async routes, lifespan events, SSE streaming |

If the user has no Weaviate instance, direct them to [Weaviate Cloud](https://console.weaviate.cloud/) for a free sandbox, then run `/weaviate:quickstart` first.

## Post-Code Review

After scaffolding a cookbook app, dispatch:
- `weaviate-schema-reviewer` — collection schema, v4 API compliance, multi-tenancy
- `rag-implementation-reviewer` — if the cookbook includes a RAG pipeline
- `security-reviewer` — if the app handles user input or external data
