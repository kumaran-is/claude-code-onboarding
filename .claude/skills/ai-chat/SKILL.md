---
name: ai-chat
description: AI chat interface patterns for Angular 22.x and Flutter 3.50.x. Use when building streaming chat UI, conversational AI assistants, copilots, token context indicators, feedback loops, multi-modal inputs, tool visualization, or AI-specific error handling. Covers streaming markdown, auto-scroll heuristics, memoized rendering, token limit UI, regeneration controls, thumbs up/down feedback, and AI error states.
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs
metadata:
  triggers: AI chat, streaming chat, conversational UI, chat interface, streaming response, token limit, AI assistant, copilot, chatbot, LLM UI, streaming markdown
  related-skills: angular-spa, flutter-mobile, agentic-ai-dev
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-22"
---

# AI Chat Interface Skill

## Iron Law

**Load this skill before building any chat interface; never hardcode streaming or message formats without verifying against the skill's patterns.**

> Server side of the stream (disconnect cancels the model call, exactly one terminal `done`/`error` frame, heartbeats, reconnect rules): `streaming-protocols` §6a. Multimodal and voice input are OPTIONAL extensions (`reference/multimodal-input.md`, `voice-ai-development`).

> **Tech Stack**: Angular 22.x (zoneless, OnPush default, signals, daisyUI 5.8.2, Tailwind 4.3.5; snippets below were compiled on 21.2.26 unless marked) | Flutter 3.50.x (Dart 3.14.0, Riverpod 3, `material_ui` 1.11.1; Flutter snippets compiled and widget-tested on 3.50.1)

## When to Activate

Load this skill when the task involves any of:
- Streaming LLM response rendering (SSE / chunked HTTP)
- Chat message list with assistant/user bubbles
- Token context window indicators
- Regenerate / stop generation controls
- Thumbs up/down feedback collection
- Multi-modal input (file/image attachment in a chat box)
- AI-specific error states (refusal, rate limit, context exceeded)
- Tool call visualization in the message thread

## Pre-Code Checklist

Before writing any component:

1. **Angular**: Read `angular-spa` skill — verify signal/OnPush/daisyUI baseline
2. **Flutter**: Read `flutter-mobile` skill — verify Riverpod/AppSpacing/colorScheme baseline
3. **Docs**: Verify any library not confirmed in this session (e.g., `marked`, `dompurify`, `flutter_markdown_plus` — `flutter_markdown` is discontinued) with `npm view <pkg> version` and the package's own README/types, or `Context7` MCP when it has quota

## Core Component Overview

| Component | Angular | Flutter |
|-----------|---------|---------|
| Message bubble list | `ChatMessageListComponent` | `ChatMessageList` widget |
| Streaming message display | `StreamingMessageComponent` | `StreamedMessageWidget` |
| Token context indicator | `TokenIndicatorComponent` | `TokenIndicatorWidget` |
| Chat input (multi-modal) | `ChatInputComponent` | `ChatInputWidget` |
| Feedback bar | `FeedbackComponent` | `FeedbackBar` widget |
| AI error display | `AiErrorComponent` | `AiErrorWidget` |
| Tool call visualization | `ToolCallCardComponent` | `ToolCallCard` widget |

## Quick Start

See `reference/quick-start.md` for entry-point wiring (Angular `ChatComponent` + Flutter `ChatScreen`).

## Key Patterns (brief — details in reference files)

### Streaming (Angular)
- Use `AbortController` to cancel in-flight SSE streams; a stopped or errored answer is shown and stored as `incomplete` — never parse, persist or act on partial structured output
- Auto-scroll: scroll only when user is within 100px of bottom
- `computed()` signal to derive rendered markdown — prevents re-parsing on every chunk
- Model output is untrusted: `marked` → `DOMPurify.sanitize` (strict allowlist, no `img`, `https:`/`mailto:` links only) → bind the **string** to `[innerHTML]`; or render as plain text. Browser-tested pipeline in `reference/streaming-patterns.md` § Rendering model output safely
- `aria-live="polite"` wraps the message list

### Streaming (Flutter)
- `AsyncNotifier` with `Stream.listen` updates `state` incrementally
- `ScrollController` + `addPostFrameCallback` for auto-scroll after frame
- Check `MediaQuery.of(context).disableAnimations` before scroll animations

### Token Context
- Angular: `TokenIndicatorComponent` uses daisyUI `progress` + `text-warning`/`text-error` classes at 80%/100% thresholds
- Flutter: `LinearProgressIndicator` with `colorScheme.error` / `colorScheme.tertiary`
- Always display "~N messages remaining" not raw token numbers

### AI Errors
- Every AI error type has a distinct UI state — see `reference/ai-error-handling.md`
- NEVER swallow AI errors silently — always show user-visible feedback with an action

### Feedback
- Angular: `signal<'up'|'down'|null>` tracks selected thumb; regenerate re-emits prompt
- Flutter: `HapticFeedback.lightImpact()` on thumb press; `colorScheme.primary` for active state

### Disclosure, uncertainty and degraded states (guardrails G17, G21, G22, G6)
- Mark AI-generated content as AI-generated in the bubble (visible label plus accessible name); keep canonical facts (record values from the API), AI explanations, AI recommendations and human decisions visually and semantically distinct
- Never show "reviewed" / "approved" unless the API returns a review record; never render certainty the response does not carry
- `NOT_FOUND`, `CONFLICTED`, `STALE` and `HUMAN_REQUIRED` responses render as their own states with an action (search, ask a person), not as an empty answer or a guess; "no data exists", "data unavailable" and "AI assist unavailable — continue with the standard form" are three different messages
- Degraded, handoff and error states are announced to screen readers (web `aria-live`; Flutter `Semantics(liveRegion: true)`), keyboard reachable and meet the same WCAG 2.2 AA bar (`accessibility-audit`); the non-AI path stays usable when AI is off

### Multi-Modal Input
- Angular: Angular CDK drag-drop for file zone; `Enter` sends, `Shift+Enter` newlines
- Flutter: `image_picker` for attachments; `maxLines: null` for auto-expanding TextField

## Reference Files

| File | Contents |
|------|----------|
| `reference/quick-start.md` | Entry-point wiring for Angular ChatComponent and Flutter ChatScreen |
| `reference/streaming-patterns.md` | Safe markdown rendering (marked → DOMPurify, browser-tested), streaming UX, auto-scroll, memoization, stop controls |
| `reference/context-management.md` | Token indicator, threshold logic, summarization trigger |
| `reference/ai-error-handling.md` | Refusal, rate limit, context exceeded, timeout, hallucination flag |
| `reference/feedback-loops.md` | Thumbs up/down, copy, regenerate — Angular & Flutter |
| `reference/multimodal-input.md` | File attach, preview chips, auto-expand textarea/field |

## Anti-Patterns — Hard Prohibitions

- **NEVER** call `bypassSecurityTrustHtml` / any `bypassSecurityTrust*` (or set `innerHTML` directly) on model, tool or user content — `marked` does not sanitize; a prompt-injected answer becomes stored XSS
- **NEVER** re-parse markdown on every streaming chunk — memoize with `computed()` / derived state
- **NEVER** auto-scroll unconditionally — it steals user scroll position mid-read
- **NEVER** display raw token counts to end users — use human-readable approximations
- **NEVER** silently ignore AI error responses — every error must log + show user feedback
- **NEVER** present AI output as canonical fact or as human-reviewed when it is not (G21)
- **NEVER** hardcode colors for error/warning states — use daisyUI tokens or `colorScheme`
- **NEVER** use constructor DI in Angular — use `inject()`
- **NEVER** use `@Input()`/`@Output()` decorators — use `input()`, `output()`, `model()` signals
- **NEVER** use raw `EdgeInsets` numeric literals in Flutter — use `AppSpacing` tokens
- **NEVER** use `Color(0x...)` literals in Flutter — use `Theme.of(context).colorScheme`

## Post-Code Review

After implementation, dispatch these reviewer agents:

| Concern | Agent |
|---------|-------|
| Angular code quality | `code-reviewer` |
| Accessibility (ARIA, keyboard nav) | `accessibility-auditor` |
| Flutter/Riverpod patterns | `riverpod-reviewer` |
| Security (file uploads, content rendering) | `security-reviewer` |
| UI/UX consistency | `ui-standards-expert` |
