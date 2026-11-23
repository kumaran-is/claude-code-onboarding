# A2UI Transport (v0.9)

First verified against `a2ui_flutter` 0.4.0, `a2ui_core` 0.8.0 and `a2ui_agent` 0.4.0. Dart blocks compile in a check app; the SSE, JSONL and action-body functions are covered by `flutter test`. Re-compiled on 2026-11-23 with `a2ui_flutter` 0.5.0, `a2ui_core` 0.9.0, `a2ui_agent` 0.5.0 and `material_ui` 1.11.1 on Flutter 3.50.1 / Dart 3.14.0 (`flutter analyze` 0 issues across every block in this skill; the widget tests pass). The 1.0 path is in `../SKILL.md` "Versioned adapter boundary".

## Overview

The packages ship no network transport. The app owns it:

```
agent ──SSE / JSONL / WebSocket──► app transport ──decode + size check──► processor.processMessages(json)
agent ◄──HTTP POST (action + capabilities + data model)── app ◄── onAction / outboundListener
```

- **Agent → app**: decode each event or line and pass it to `processor.processMessages`. It accepts a lone envelope, a list of envelopes, the `{"messages": [...]}` wrapper, or parsed `AgentToRendererMessage` objects.
- **App → agent**: user actions and errors, wrapped in `RendererToAgentMessagePayload`, plus the renderer's capabilities and (for surfaces that asked) its data model.
- **Model text → messages**: only when the app calls a model itself; `a2ui_agent`'s `ResponseStream` parses the model's reply (see `genui-conversation-orchestration.md`).

## v0.9 message reference

Every message carries `"version": "v0.9"` and exactly one of these keys:

| Message | Body | Effect |
|---|---|---|
| `createSurface` | `surfaceId`, `catalogId`, optional `theme`, optional `sendDataModel` | New surface bound to one registered catalog |
| `updateComponents` | `surfaceId`, `components: [{id, component, ...props}]` | Adds or replaces components by id; the tree starts at id `root` |
| `updateDataModel` | `surfaceId`, optional `path`, optional `value` | Writes the data model (no `path`: whole model; no `value`: delete) |
| `deleteSurface` | `surfaceId` | Removes the surface; an unknown id is a no-op |

```json
[
  {"version": "v0.9", "createSurface": {"surfaceId": "signup", "catalogId": "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json", "sendDataModel": true}},
  {"version": "v0.9", "updateDataModel": {"surfaceId": "signup", "value": {"email": ""}}},
  {"version": "v0.9", "updateComponents": {"surfaceId": "signup", "components": [
    {"id": "root", "component": "Column", "children": ["title", "email", "submit"]},
    {"id": "title", "component": "Text", "text": "Newsletter", "variant": "h3"},
    {"id": "email", "component": "TextField", "label": "Email", "value": {"path": "/email"},
     "checks": [{"condition": {"call": "email", "args": {"value": {"path": "/email"}}}, "message": "Enter a valid email address."}]},
    {"id": "submit_label", "component": "Text", "text": "Subscribe"},
    {"id": "submit", "component": "Button", "variant": "primary", "child": "submit_label",
     "action": {"event": {"name": "subscribe", "context": {"email": {"path": "/email"}}}}}
  ]}}
]
```

Every message in a payload is parsed before any is applied, so a malformed envelope rejects the whole payload. Messages are then applied in order; one that fails validation leaves its surface as it was and throws, and the messages before it stay applied. Full protocol notes shared with the Angular skill: `../../a2ui-angular/reference/a2ui-protocol.md`.

## Agent → app: Server-Sent Events

Each SSE event's `data:` lines hold one JSON array of messages. Reject oversized events before decoding:

```dart
import 'dart:convert';

import 'package:a2ui_core/a2ui_core.dart';
import 'package:a2ui_flutter/a2ui_flutter.dart';

/// Decodes a Server-Sent Events body in which each event's `data:` lines hold
/// one JSON array of v0.9 messages. Rejects an event larger than
/// [maxEventChars] before decoding it.
Stream<Object?> a2uiPayloads(
  Stream<List<int>> body, {
  int maxEventChars = 256 * 1024,
}) async* {
  final data = StringBuffer();
  await for (final line
      in body.transform(utf8.decoder).transform(const LineSplitter())) {
    if (line.startsWith('data:')) {
      if (data.isNotEmpty) data.write('\n');
      data.write(line.substring(5).trimLeft());
      if (data.length > maxEventChars) {
        throw FormatException('A2UI event exceeds $maxEventChars characters');
      }
    } else if (line.isEmpty && data.isNotEmpty) {
      final String event = data.toString();
      data.clear();
      yield jsonDecode(event);
    }
  }
  if (data.isNotEmpty) yield jsonDecode(data.toString());
}

/// Applies each payload of [body] to [processor]. A malformed or rejected
/// payload ends the stream with an error the caller must show.
Future<void> applyStream(
  MessageProcessor<ComponentImplementation> processor,
  Stream<List<int>> body,
) async {
  await for (final Object? payload in a2uiPayloads(body)) {
    processor.processMessages(payload); // throws A2uiError on a bad message
  }
}
```

`body` is the byte stream of the HTTP response (for example `StreamedResponse.stream` from `package:http`). The caller wraps `applyStream` in `try`, catches `FormatException` and `A2uiError`, logs them and shows an error with a retry. Tested: a valid event creates the surface; a 300 000-character event throws `FormatException` and is never decoded.

## Agent → app: JSONL

One message envelope per line:

```dart
/// JSONL: one v0.9 message envelope per line. Blank lines are skipped.
Future<void> applyJsonl(
  MessageProcessor<ComponentImplementation> processor,
  Stream<List<int>> body, {
  int maxLineChars = 256 * 1024,
}) async {
  await for (final line
      in body.transform(utf8.decoder).transform(const LineSplitter())) {
    if (line.trim().isEmpty) continue;
    if (line.length > maxLineChars) {
      throw FormatException('A2UI line exceeds $maxLineChars characters');
    }
    processor.processMessages(jsonDecode(line)); // a lone envelope is accepted
  }
}
```

When components arrive across several lines (parent before child), a strict `validationConfig` rejects the dangling reference; use the streaming config in `genui-security.md`.

## App → agent: actions, capabilities and data model

A user action reaches `processor.model.onAction` (or the `onAction:` constructor callback) as an `A2uiRendererAction` with `name`, `surfaceId`, `sourceComponentId`, `timestamp`, the resolved `context`, and optional `catalogId` / `metadata`. Report it to the agent with the renderer's v0.9 capabilities:

```dart
/// The JSON body that reports a user action to the agent, with the renderer's
/// v0.9 capabilities and the data model of surfaces created with
/// `sendDataModel: true`.
Map<String, Object?> actionRequestBody(
  MessageProcessor<ComponentImplementation> processor,
  A2uiRendererAction action,
) {
  const A2uiProtocolVersion v0_9 = A2uiProtocolVersion.v0_9;
  return {
    'a2ui': RendererToAgentMessagePayload([
      ActionMessage(version: v0_9.jsonValue, action: action),
    ]).toJson(),
    'metadata': {
      'a2uiClientCapabilities': processor
          .getRendererCapabilities(const CapabilitiesOptions(versions: [v0_9]))
          .toJson(),
      'a2uiClientDataModel': ?processor.getRendererDataModel(version: v0_9),
    },
  };
}
```

- `a2uiClientCapabilities` tells the agent which catalogs this renderer supports. Send it on the first request of a conversation and on every reconnect. `a2ui_agent`'s `readRendererCapabilities` reads this key for v0.9.
- `a2uiClientDataModel` is null when no surface asked for `sendDataModel`; the `?` null-aware map entry (Dart 3.8+) omits the key then.
- The envelope shape (`a2ui` + `metadata`) is this app's contract with its own agent server; agree it with the server team. The A2UI parts are `RendererToAgentMessagePayload(...).toJson()` and the two metadata keys.
- **Check `action.name` against the app's own allowlist** before acting on it locally (opening a camera, navigating). Forwarding an unknown name to the agent is harmless; acting on it is not.
- For one outbound channel, construct the processor with `outboundListener:` and `unifiedOutbound: true`: the listener then receives every `RendererToAgentMessage` (actions, errors, function traffic). `unifiedOutbound` without `outboundListener` throws `ArgumentError`.

## Connection lifecycle

| State | App does |
|---|---|
| Request sent | Show a loading indicator on the conversation, not over existing surfaces |
| Streaming | Apply each payload as it arrives; surfaces update progressively |
| Stream ends | Clear the loading state |
| Payload rejected (`A2uiError`) | Stop applying that stream, log `code` + `message`, show an error with retry; keep surfaces already applied |
| Network error / timeout | Show reconnect; on retry send capabilities again |
| Conversation closed | Cancel the HTTP stream, `processor.dispose()` |

Set a connect timeout and an idle timeout (no event for N seconds) on the HTTP client; an agent that stops mid-stream must not leave the UI spinning. Retry with backoff and a cap; never retry a request whose action had side effects unless the server makes it idempotent.

## Backend contract (agent server)

Agree with the agent team:

1. The endpoint and stream format (SSE with one JSON array per event, or JSONL with one envelope per line).
2. That the agent writes `"version": "v0.9"` on every message and only `catalogId`s the app advertised in `a2uiClientCapabilities`.
3. The action request body (above) and how the agent correlates it with the conversation (a conversation id the server issues; never a user-supplied identifier the server trusts).
4. Server-side limits: maximum payload size, components per surface, surfaces per conversation, and rate limits. Enforce them on the server and again in the app.

Python agents built with Google ADK: see the `google-adk` skill. A Dart server can use `a2ui_agent` (`A2uiGenerator.createProcessor` with the capabilities the app sent) to prompt the model and validate its output before streaming it.
