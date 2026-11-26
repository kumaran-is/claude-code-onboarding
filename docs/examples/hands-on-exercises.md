# Hands-on exercises

Practice the toolkit after the README quick start. Run these inside a Claude Code session in this repository.

## 16. Hands-On Exercises

Work through these exercises to get familiar with Claude Code. Each one uses different components from this kit.
These exercises follow a deliberate progression to help you understand **which component to use for and when**:

| Exercises | Focus | Components Introduced |
|-----------|-------|----------------------|
| **1–4** | Single-stack scaffolding | Slash Commands, Skills (auto), Agents |
| **5** | Multi-stack integration | Chaining commands + agents across layers |
| **6** | External tooling | MCP Servers (Context7) |
| **7** | Design & review | Review agents, architecture patterns |
| **8** | AI agent development | Agentic AI stack, advanced agent patterns |
| **9** | Domain modeling | DDD skill, cross-cutting analysis |
| **10** | Full workflow | All components working together |

**Exercises 1–4 are independent** — do them in any order based on your stack. **Exercises 5+** build on concepts from earlier exercises, so work through them sequentially.

### Exercise 1: Scaffold a Flutter Fitness App

**Components used:** Slash Command → Skill (auto) → Sub-agent
> **How it works:** The slash command kicks off scaffolding. Based on task context, Claude automatically activates relevant skills and sub-agents as needed — you just keep prompting naturally.

```
> /scaffold-flutter-app fitness tracker
```

Then iterate:

```
> Add a workout logging feature with Firestore integration
> Create the database schema for tracking workouts, exercises, and user stats
> Add a dashboard screen showing weekly workout summary with charts
```

### Exercise 2: Build a Weather REST API (Java)

**Components used:** Slash Command → Sub-agent → Skill (auto)

Scaffold first, then use the `@java-spring-api` agent for domain-specific implementation:

```
> /scaffold-spring-api weather-service
> @java-spring-api Add a WeatherController that accepts a city name and returns mock weather data with temperature, humidity, and condition
> Add integration tests for the weather endpoint
```

### Exercise 3: Build a Todo API (NestJS)

**Components used:** Slash Command → Sub-agent

```
> /scaffold-nestjs-api todo-service
> @nestjs-api Add a Todo feature module with CRUD endpoints, Prisma model, DTO validation, and service
> Add Vitest integration tests for create and list endpoints
> Add a PATCH endpoint to mark todos as complete
```

### Exercise 4: Build an Analytics API (Python)

**Components used:** Slash Command → Sub-agent

```
> /scaffold-python-api analytics-service
> @python-dev Add an async endpoint that accepts event data and stores it with timestamps
> Create a Pydantic model for events with type, payload, and metadata
> Add pytest tests for the event endpoints
```

### Exercise 5: Design a Full-Stack E-Commerce System

**Components used:** Slash Command → Sub-agent → Skill (auto) → MCP Server

This exercise chains multiple components together — architecture design, database schema, API scaffolding, and implementation:

```
> /design-architecture An e-commerce platform with product catalog, shopping cart, checkout, and order tracking. Angular SPA for web, Flutter for mobile, Spring Boot backend.
> /design-database e-commerce platform with products, categories, users, orders, order items, payments, and shipping
> /scaffold-spring-api ecommerce-api
> @java-spring-api Create CRUD endpoints for Products with name, description, price, category, and image URL
```

### Exercise 6: Pull Live Docs with Context7 (MCP)

**Components used:** MCP Server (Context7)

Append `use context7` to any prompt to fetch up-to-date, version-specific documentation instead of relying on Claude's training data:

```
> Create a Spring Boot WebFlux endpoint that uses Spring Security with JWT. use context7
> Build an Angular component using the new Angular signals API. use context7
> Set up Firebase App Check in Flutter. use context7
> Create a FastAPI endpoint with async SQLAlchemy. use context7
> Create a NestJS guard with JWT validation using @nestjs/passport. use context7
```

### Exercise 7: Design & Review Architecture

**Components used:** Sub-agents (`@architect`, `@database-designer`)

Use specialized agents for design and review tasks that benefit from isolated, focused context:

```
> @architect Review the current project structure and suggest improvements
> @architect Design a real-time notification system that works across Angular web and Flutter mobile using Firebase Cloud Messaging
> @database-designer Design the notification schema with PostgreSQL for persistence and Firestore for real-time delivery
```

### Exercise 8: Build an AI Agent Service (Agentic AI)

**Components used:** Slash Command → Sub-agent → Skill (auto) → MCP Server

Scaffold a production AI agent service, then build out a ReAct agent with RAG and tools:

```
> /scaffold-agentic-ai research-agent
> @agentic-ai-dev Add a web search tool and a database query tool with Pydantic input validation
> @agentic-ai-dev Build an Agentic RAG system with query routing, document grading, and web search fallback
> @agentic-ai-dev Add guardrails — prompt injection detection, PII redaction, and output validation
> @agentic-ai-dev Write tests for the ReAct agent: basic invoke, tool usage, iteration limit, and error recovery
```

Then review your work:

```
> @agentic-ai-reviewer Review the agent service for graph correctness, safety, cost, and production readiness
```

### Exercise 9: Domain-Driven Design with DDD Architect

**Components used:** Skill (ddd-architect) → Sub-agents (`@architect`, `@database-designer`)

Use the DDD Architect skill to decompose a complex domain into bounded contexts, aggregates, and integration patterns — then hand off to implementation agents:

```
> Perform a full DDD analysis for an online food delivery platform. The system handles restaurant menus, customer ordering, real-time delivery tracking, payments, ratings and reviews, and a loyalty program. Tech stack: Spring Boot microservices, Angular web, Flutter mobile, PostgreSQL, Firebase for real-time.
```

Claude activates the `ddd-architect` skill automatically and walks through strategic → tactical → technical phases. Follow up to drill deeper:

```
> Show me the context map with all integration patterns between Order, Delivery, and Payment contexts
> Design the Order aggregate with invariants — what rules must hold when placing, modifying, or cancelling an order?
> Which contexts should communicate via domain events vs. synchronous API calls? Justify each.
> Generate the implementation roadmap — which bounded contexts should we build first and why?
```

Then use the outputs to drive implementation:

```
> @database-designer Design the PostgreSQL schema for the Order bounded context based on the DDD tactical design
> @architect Design the event-driven integration between Order, Payment, and Delivery contexts using the context map
```

### Exercise 10: Add a Feature End-to-End

**Components used:** Slash Command → all components in action

This is the real-world workflow — a single command that triggers scaffolding, skills, agents, and MCP servers working together:

```
> /add-feature User profile management — users can update their name, avatar, and preferences. Backend API + Angular settings page + Flutter profile screen
```

### Exercise 11: Build an A2UI Renderer (Agent-to-User Interface)

**Components used:** Slash Command + Agent + Skill + MCP

A2UI is Google's declarative protocol (1.0, with v0.9.x still supported) that lets AI agents describe rich, interactive UIs as structured JSON instead of generating executable code. The agent sends four message types (`createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface`); your app validates each component against an approved catalog and renders it with native components. One framework-neutral catalog (`genui-contract` skill) serves Angular, React and Flutter, from one shared backend or from independent backends. Start a cross-platform feature with `/scaffold-genui-feature`, and gate it with `/audit-a2ui-parity` and `/validate-genui-feature`.

**v0.9 basic catalog:** Text, Image, Icon, Video, AudioPlayer, Row, Column, List, Card, Tabs, Modal, Divider, Button, TextField, CheckBox, ChoicePicker, Slider, DateTimeInput.

- Each component is a flat object, for example `{"id": "title", "component": "Text", "text": "Hello"}`.
- Children are an array of IDs, `["id1", "id2"]`, or a template `{"componentId": "row", "path": "/items"}`.
- A value is either a literal or a data binding: `"Hello"` or `{"path": "/data/pointer"}`.

**Scaffold with the slash command:**

```
> /scaffold-a2ui travel-assistant
```

This creates a complete A2UI feature module: models (`SurfaceState`, `A2UIMessage`, `A2UIAgentAction`), catalog service, sanitizer, recursive renderer, agent service (REST + SSE/JSONL), chat page, routes, and tests.

**Or use the specialist agent for custom work:**

```
> @a2ui-angular Build an A2UI renderer that supports flight cards, hotel listings, and booking forms. The agent backend is at /api/travel/chat and streams via SSE as JSONL.
```

```
> @a2ui-angular Add a "table" component type (Angular extension, not in core spec) to our existing A2UI catalog and renderer. Use daisyUI table classes.
```

```
> @a2ui-angular Review our A2UI renderer for security issues — make sure every component is validated against the catalog allowlist, actions are on the action allowlist, and each stream uses exactly one protocol version (1.0, or v0.9.x for a client that declares only v0.9).
```

**Key concept:** A2UI payloads are untrusted. Every component type from the agent is validated against a client-side catalog allowlist before rendering. An unknown component rejects the message and the user sees an error, never a silent skip. Agent-provided code is never executed. An action is a v0.9 client message, `{"version": "v0.9", "action": {"name", "surfaceId", "sourceComponentId", "timestamp", "context": {...}}}`. The server authorizes every action, because the renderer is not a security boundary.

### Exercise 12: Build a Google ADK Agent Service

**Components used:** Slash Command + Agent + Skill + MCP (Context7)

Google ADK (Agent Development Kit) is Google's framework for building Gemini-powered agents. Unlike LangGraph's graph-based state machines, ADK uses composable agent primitives: `SequentialAgent` for pipelines, `ParallelAgent` for concurrent analysis, `LoopAgent` for iterative refinement, and `transfer_to_agent` for multi-agent routing. Tools are plain Python functions — no decorators needed.

**Scaffold a new ADK service with the slash command:**

```
> /scaffold-google-adk travel-agent
```

This creates a complete ADK project: `Agent` with `gemini-2.5-flash`, `FunctionTool` examples, `InMemorySessionService`, FastAPI `/chat` and `/stream` (SSE) endpoints, `InMemoryRunner`-based tests, `.env` template, and Dockerfile.

**Or build directly with the specialist agent:**

```
> @google-adk Build a research pipeline using SequentialAgent: researcher → writer → editor. Each agent should pass its output via output_key so the next stage can read it from session state.
```

```
> @google-adk Add a ParallelAgent that runs technical_analyst, market_analyst, and risk_analyst concurrently. Wire it into a SequentialAgent so a synthesizer receives all three analyses and produces a final report.
```

```
> @google-adk Expose the agent via FastAPI — POST /chat returns the final response, GET /stream returns SSE. Use InMemorySessionService. Close the runner in the lifespan shutdown.
```

```
> @google-adk Add a before_model_callback to enforce rate limiting (max 100 calls per session) and an on_tool_error_callback that returns a structured error dict instead of raising.
```

```
> @google-adk Write tests for the pipeline using InMemoryRunner — basic response, tool invoked, output_key passed between agents, LoopAgent exits within max_iterations, FastAPI /chat returns 200.
```

**Key concepts:**
- Tools are plain Python functions — full docstring (Args + Returns) required for schema auto-generation
- `ToolContext` is auto-injected when typed `tool_context: ToolContext` — access session state via `tool_context.state`
- `output_key="key"` stores an agent's final output into session state; downstream agents read it as `{key}` in `instruction`
- `InMemoryRunner` for tests — never call real Gemini API in unit tests
- Always `await runner.close()` in FastAPI lifespan shutdown to release MCP connections

**Review your work:**

```
> @agentic-ai-reviewer Review the ADK agent service for correctness, safety guardrails, and production readiness
> @security-reviewer Check tool input validation and session state handling in the ADK service
```

### Exercise 13: Build a Three.js 3D Scene (Angular/Web)

**Components used:** Skills (auto-activated) + Agent + MCP (Context7)

Three.js is a JavaScript/WebGL library for building 3D scenes in the browser. When you add `three` to your Angular project's `package.json`, the `threejs-*` skills activate automatically based on context — no slash command needed.

**Skills that auto-activate** (10 skills in `.claude/skills/`):

| Skill | Activates when you ask about… |
|-------|-------------------------------|
| `threejs-fundamentals` | Scene setup, camera, renderer, animation loop |
| `threejs-geometry` | Shapes, BufferGeometry, custom meshes, instancing |
| `threejs-materials` | PBR materials, ShaderMaterial, transparency |
| `threejs-lighting` | Lights, shadows, environment maps |
| `threejs-textures` | Texture loading, UV mapping, render targets |
| `threejs-animation` | AnimationMixer, keyframe clips, GLTF animations |
| `threejs-loaders` | GLTFLoader, DRACOLoader, async asset loading |
| `threejs-shaders` | GLSL, uniforms, custom vertex/fragment shaders |
| `threejs-postprocessing` | EffectComposer, bloom, depth-of-field |
| `threejs-interaction` | Raycasting, mouse/touch input, OrbitControls |

**Sample prompts — ask these after adding `three` to your project:**

```
> Create a basic Three.js scene with a rotating cube and directional lighting
```

```
> Set up a Three.js scene in Angular that loads a GLTF model with Draco compression and plays its idle animation
```

```
> Add OrbitControls so the user can rotate the camera with mouse drag
```

```
> Create a custom ShaderMaterial with a fresnel edge glow effect
```

```
> Add post-processing: bloom on bright objects and a subtle vignette
```

```
> Optimize the scene: 500 trees using InstancedMesh instead of individual meshes
```

**Add Three.js to an Angular project:**
```bash
npm install three @types/three
npm install three/addons  # for GLTFLoader, OrbitControls, EffectComposer etc.
```

> Three.js uses `three/addons/` import paths as of r150+. Skills are audited against r160+ — no deprecated patterns.

---

### Exercise 14: Build a three\_dart 3D Scene (Flutter)

**Components used:** Skills (auto-activated) + Agent + MCP (Dart)

`three_dart` is a Dart port of Three.js for Flutter. Same API concepts as Three.js — Scene, Camera, Mesh, Material, Geometry — but in Dart syntax with Flutter widget integration via `ThreeDartWidget`. When you add `three_dart` to `pubspec.yaml`, the `three-dart-*` skills activate automatically.

**Skills that auto-activate** (5 skills in `.claude/skills/`):

| Skill | Activates when you ask about… |
|-------|-------------------------------|
| `three-dart-fundamentals` | Scene setup, PerspectiveCamera, ThreeDartWidget, animation loop |
| `three-dart-geometry` | Built-in shapes, BufferGeometry, InstancedMesh |
| `three-dart-materials` | MeshStandardMaterial, ShaderMaterial, transparency |
| `three-dart-animation` | AnimationMixer, AnimationClip, crossfade |
| `three-dart-loaders` | GLTFLoader, TextureLoader, Flutter asset loading |

**Sample prompts — ask these after adding `three_dart` to your Flutter project:**

```
> Set up a three_dart scene in Flutter with a rotating sphere and ambient + directional lighting
```

```
> Load a GLTF model from Flutter assets using GLTFLoader and play its first animation clip
```

```
> Create a scene with 500 instanced tree meshes using InstancedMesh for a single draw call
```

```
> Add a MeshStandardMaterial with a roughness map loaded from assets/textures/
```

```
> Write a crossfade between two AnimationClips — walk → run over 0.3 seconds
```

```
> Add proper dispose() cleanup to the ThreeDartWidget to prevent WebGL context leaks on mobile
```

**Add three_dart to a Flutter project (`pubspec.yaml`):**
```yaml
dependencies:
  three_dart: ^0.0.15
  flutter_gl: ^0.0.10
  three_dart_jsm: ^0.0.15  # for GLTFLoader, DRACOLoader
```

> three_dart mirrors the Three.js API surface. The `three-dart-fundamentals` skill includes a JS↔Dart API mapping table so developers familiar with Three.js can ramp up instantly.

---

### What's Next?

You've used every component in the kit — agents, skills, commands, hooks, and MCP servers. Now apply it to your own project:

1. **Copy the config** into your project (Option B from [Clone this repo](../../README.md#clone-this-repo)):
   ```bash
   cp -r .claude/ your-project/.claude/
   cp CLAUDE.md your-project/
   cp .mcp.json your-project/
   ```
2. **Trim what you don't need** — remove agents, skills, and commands for stacks you don't use. See [Removing Components You Don't Need](../engineering/customizing.md#removing-components-you-dont-need).
3. **Write your own CLAUDE.md** — replace the tech stack, conventions, and rules with your project's. See [Claude Code memory docs](https://code.claude.com/docs/en/memory).
4. **Set up credentials** — copy `.env.example` to `.env`, configure MCP server tokens as environment variables
5. **Verify** — run Claude Code and check that everything loads:
   ```
   > /project-status
   > /mcp
   > What agents and skills are available?
   ```
6. **Iterate** — your CLAUDE.md and skills will evolve as you discover what works for your team. Treat them like living documentation — PR-reviewed and version-controlled
