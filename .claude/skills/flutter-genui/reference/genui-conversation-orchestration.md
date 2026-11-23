# A2UI Conversation Orchestration (Flutter, v0.9)

Verified against `a2ui_flutter` 0.4.0, `a2ui_core` 0.8.0 and `a2ui_agent` 0.4.0. Dart blocks compile in a check app; the in-app model example is covered by a `flutter test` that streams a reply in 7-character chunks.

## Overview

The packages provide no conversation object. The app owns the loop, and picks one of two topologies:

| Topology | Who calls the model | Packages in the app | Use when |
|---|---|---|---|
| **Agent server** | A backend agent (ADK, LangGraph, Dart) | `a2ui_core` + `a2ui_flutter` | Default. Keys, tools, retrieval and policy stay on the server |
| **In-app model** | The app (for example through Firebase AI Logic) | + `a2ui_agent` | No agent server; the app prompts the model and parses A2UI from its reply |

Never ship a model provider's secret API key in the app binary. The in-app topology needs a client SDK designed for that (with App Check or an equivalent), not a raw key.

## Conversation lifecycle (both topologies)

```
user text ──► request (+ a2uiClientCapabilities) ──► agent / model
                                                        │ streams v0.9 messages (and plain text)
     ◄── surfaces render (A2uiSurface) ◄── processor.processMessages ◄──┘
user input ──► data model (bindings)
user tap   ──► onAction ──► app allowlist ──► next request (action + capabilities + data model)
```

State the app keeps per conversation:

| State | Where |
|---|---|
| Processor and surfaces | One `MessageProcessor`, disposed with the conversation |
| Chat transcript (user text, assistant text, which surface belongs to which turn) | App model (list of messages with an optional `surfaceId`) |
| Loading / error | App state; one in-flight request at a time per conversation |
| Conversation id | Issued by the server; sent with every request |

## Agent-server topology

The app sends the user's text (or an action) and applies the streamed reply:

1. On send: set loading, POST the text with `a2uiClientCapabilities` (see `actionRequestBody` in `genui-a2ui-transport.md` for the metadata keys).
2. Read the response with `applyStream` (SSE) or `applyJsonl`; each payload goes to `processor.processMessages`.
3. On `onAction`: check the name against the app's allowlist, then POST the action body; apply the reply the same way.
4. On `A2uiError` / `FormatException` / network error: clear loading, show the error with retry, keep the surfaces already shown.

## In-app model topology (`a2ui_agent`)

`a2ui_agent` teaches the model the catalog (`promptSnippet`) and parses its streamed reply. With `RendererState.of(renderer)` the parsed messages are applied straight to the renderer's processor, so each message is checked and applied once:

```dart
import 'package:a2ui_agent/a2ui_agent.dart';
import 'package:a2ui_core/a2ui_core.dart';
import 'package:a2ui_flutter/a2ui_flutter.dart';
import 'package:a2ui_flutter/v0_9/basic_catalog.dart';

/// For an app that calls a model itself (no agent server): teaches the model
/// A2UI and the catalog, and parses its streamed reply straight into the
/// renderer's processor.
class InAppModelTurns {
  InAppModelTurns(this.renderer, CatalogImplementation catalog)
    : _agent =
          A2uiGenerator(
            catalogs: [CatalogConfig(catalog)],
            inferenceFormatFactory: const DirectJsonFormatFactory(
              progressiveKeys: {'text', 'label'},
            ),
          ).createProcessor(
            A2uiRendererCapabilities.forCatalogIds([
              catalog.id,
            ], version: A2uiProtocolVersion.v0_9),
          );

  final MessageProcessor<ComponentImplementation> renderer;
  final A2uiRequestProcessor _agent;

  /// Append to the app's own system instructions.
  String get promptSnippet => _agent.promptSnippet;

  /// Feeds one streamed model reply. Surfaces appear in `renderer.model` as
  /// they stream; the returned string is the reply's plain text.
  Future<String> run(Stream<String> chunks) async {
    final ResponseStream stream = _agent.openStream(
      state: RendererState.of(renderer),
    );
    final reply = StringBuffer();
    void show(List<ResponsePart> parts) {
      for (final part in parts) {
        if (part case TextPart(:final String text)) reply.write(text);
      }
    }

    await for (final String chunk in chunks) {
      show(stream.feed(chunk)); // throws A2uiError on a rejected block
    }
    show(stream.close());
    return reply.toString();
  }
}
```

Usage: `InAppModelTurns(processor, basicCatalog())`, where `processor` is the renderer's `MessageProcessor`.

- **Formats.** `A2uiGenerator` defaults to the compact Express format (`ExpressFormatFactory`). `DirectJsonFormatFactory` makes the model write v0.9 JSON inside an `<a2ui-json>` block; `progressiveKeys` heals those string properties while they stream, so text appears as the model writes it. Tested: a reply `Here you go. <a2ui-json>[…]</a2ui-json> Done.` fed in 7-character chunks created the surface, and the returned text contained the prose but no JSON.
- **Parts.** `feed` and `close` return `ResponsePart`s: `TextPart(text)` for prose and `A2uiPart(a2ui)` for messages. With a renderer state the messages are already applied; without one, apply each with `renderer.processMessages(AgentToRendererMessagePayload.of(message))`.
- **Errors.** If `feed` or `close` throws, the stream has ended; the thrown `A2uiError`'s `partialResults` holds parts made ready before the failure. To keep reading after a rejected block, use `openContinuingStream`, which returns an `ErrorPart` in its place. `StreamedAnswer(processor, renderer:)` keeps text, surfaces and errors of one answer in order.
- **Actions back to the model.** Turn an `A2uiRendererAction` into the next user turn (for example its `name` and `context` as JSON) and send it with the transcript.
- **v0.9 limits.** Express on v0.9 cannot write a function call as a statement of its own (there is no v0.9 message for it).

## Riverpod

Riverpod is optional. If the app uses it:

- Own the processor in a `Provider` with `ref.onDispose(processor.dispose)` and expose the surface list from a `Notifier` (full code in `genui-state-binding.md`).
- Keep the conversation (transcript, loading, error) in an `AsyncNotifier` or `Notifier` that reads the processor provider and calls the transport. Expose loading and error explicitly; never return an empty transcript on failure.
- Scope the providers to the conversation screen (or use `autoDispose`) so leaving the screen disposes the processor and cancels the stream.

## Streaming vs whole replies

| Mode | Behaviour | Validation config |
|---|---|---|
| Streamed (SSE events, JSONL lines, `ResponseStream`) | Surfaces build progressively | `streamingValidation` when a parent can arrive before its child (`genui-security.md`) |
| Whole reply (one JSON array per turn) | Surface appears at once | Strict |

## Error handling in the loop

| Failure | App behaviour |
|---|---|
| Request fails (network, 5xx, timeout) | Clear loading, show retry; the transcript keeps the user's message |
| Payload or block rejected (`A2uiError`) | Log `code` + `message`, show "could not display", keep earlier surfaces; offer the fallback form |
| Model reply has text but no surface | Show the text; that is a valid turn |
| Action not in the app's allowlist | Log it, do not act locally; forward to the agent only if the protocol requires |
| User leaves mid-stream | Cancel the request, dispose the processor |

## Fallback: static form

When the agent path is unavailable (stream fails, payload rejected, feature flag off), show an app-owned form with the essential fields so the user can still complete the task. Mark the submission as not agent-classified so downstream processing can route it. Never leave the user on a spinner or an empty surface.
