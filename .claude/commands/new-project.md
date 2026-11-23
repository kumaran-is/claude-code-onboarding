---
description: Detect project type from natural language and route to the correct scaffold command. Say "new-project flutter fitness tracker" or "new-project python api" and it routes automatically.
argument-hint: "[project description, e.g. 'flutter todo app' or 'python api for invoices']"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# New Project — Keyword Router

**Request:** $ARGUMENTS

## Step 1 — Detect Project Type

Analyze `$ARGUMENTS` using this keyword matrix. Rows run from most to least specific; match the FIRST row that fits (so "agent-driven UI" reaches the GenUI rows before the Agentic AI row, and "react native" before "react"):

| Keywords in request | Project Type | Route to command |
|---------------------|--------------|-----------------|
| `genui`, `a2ui`, `agent ui`, `agent-driven ui` + more than one platform | GenUI feature (existing apps) | `/scaffold-genui-feature` |
| `flutter` + `genui`/`a2ui` | Flutter A2UI feature (existing app) | `/scaffold-genui` |
| `a2ui`, `agent ui`, `agent-driven ui` (Angular or unspecified) | A2UI Angular feature (existing app) | `/scaffold-a2ui` |
| `flutter package`, `shared_ui`, `shared_core` | Flutter shared package item | `/scaffold-flutter-package` |
| `flutter`, `dart`, `ios app`, `android app` | Flutter Mobile | `/scaffold-flutter-app` |
| `react native`, `expo`, `rn app` | React Native | Load `mobile-developer` skill |
| `react`, `vite`, `react spa` | React SPA | `/scaffold-react-app` |
| `nestjs`, `nest`, `node api`, `typescript api` | NestJS API | `/scaffold-nestjs-api` |
| `worker`, `consumer`, `pub/sub`, `scheduled job` (Python) | Python worker | `/scaffold-python-worker` |
| `adk`, `gemini agent`, `google adk` | Google ADK Agent | `/scaffold-google-adk` |
| `rag pipeline`, `pgvector`, `weaviate`, `embeddings` | RAG pipeline | `/rag-design` (ADR) then `/scaffold-rag-pipeline` |
| `agent`, `langchain`, `langgraph`, `ai agent` | Agentic AI | `/scaffold-agentic-ai` |
| `python`, `fastapi`, `django`, `flask` | Python API | `/scaffold-python-api` |
| `java`, `spring`, `spring boot` | Java Spring API | `/scaffold-spring-api` |
| `angular`, `spa`, `web app`, `dashboard` | Angular SPA | `/scaffold-angular-app` |
| `database`, `schema`, `postgres`, `sql` | Database Schema | `/design-database` |
| No clear match | Ambiguous | Ask one clarifying question (see Step 2) |

## Step 2 — If ambiguous

Ask exactly ONE question:
```
I need one clarification: what is the primary technology?
Options: Flutter mobile / NestJS API / Python FastAPI / Java Spring / Angular SPA / React SPA / AI Agent
```

Do not ask multiple questions. One answer is enough to route.

## Step 3 — Route

Once type is determined:

1. **Extract the app name** from `$ARGUMENTS` (everything after the tech keyword, e.g. "fitness tracker" from "flutter fitness tracker"). Use as the project name for the scaffold command.

2. **Run the Plan Verification gate first:**
   ```
   🔴 Does docs/plans/YYYY-MM-DD-<project-name>.md exist?
   NO → Create it before scaffolding (list: feature scope, key screens/endpoints, data models)
   YES → Verify it is current, then proceed
   ```

3. **Execute the routed command** with the extracted name as argument. Scaffold commands run in the main session only (subagents cannot invoke slash commands; raw `flutter create` / `ng new` / `nest new` are blocked by `block-raw-scaffold.sh`). The GenUI and shared-package rows add to an EXISTING app: confirm its path first.
4. **Verify the scaffold:** run `/verify quick` in the new project and report each stack's status with its own exit code before saying the project is ready.

## Step 4 — Flutter-specific additions

If routed to Flutter (`/scaffold-flutter-app`):
- Also load `mobile-design` skill and complete Mobile Checkpoint before writing any UI
- Run MFRI scoring (score must be ≥ 3 to proceed)
- Before scaffolding: `flutter --version` must report Flutter 3.50.x / Dart 3.14.x (the toolkit's verified baseline); an older SDK is BLOCKED, not silently scaffolded with older pins
- After scaffold: load `flutter-mobile` skill for implementation patterns

## Examples

| User input | Detected type | Action |
|------------|--------------|--------|
| `new-project flutter fitness tracker` | Flutter Mobile | `/scaffold-flutter-app fitness-tracker` |
| `new-project python invoice api` | Python API | `/scaffold-python-api invoice-api` |
| `new-project nestjs user management` | NestJS API | `/scaffold-nestjs-api user-management` |
| `new-project angular admin dashboard` | Angular SPA | `/scaffold-angular-app admin-dashboard` |
| `new-project langgraph support agent` | Agentic AI | `/scaffold-agentic-ai support-agent` |
| `new-project react orders portal` | React SPA | `/scaffold-react-app orders-portal` |

Use instead when: `/add-feature` — the project already exists.
| `new-project java spring orders` | Java Spring | `/scaffold-spring-api orders` |
