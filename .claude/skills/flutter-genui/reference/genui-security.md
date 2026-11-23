# A2UI Security (Flutter, v0.9)

Verified against `a2ui_flutter` 0.4.0 and `a2ui_core` 0.8.0. Dart blocks compile in a check app; each rejection below is a `flutter test` with a positive control where one applies.

## Threat model

Treat any agent outside your direct control as untrusted, and a model's output as untrusted even when you run the agent: prompt injection in the conversation or in retrieved content can steer what it writes. The `a2ui_flutter` README states the same: a malicious agent can imitate a legitimate interface to deceive users, or send layouts heavy enough to degrade the app.

| Threat | Vector | Control |
|---|---|---|
| Component injection | A component name the app did not register | Catalog allowlist + strict `validationConfig` |
| Catalog spoofing | `createSurface` naming a catalog the app did not register | Rejected by the processor (`A2uiError`) |
| Protocol confusion | Messages of another version, or without an adapter | Rejected; set `defaultVersion` and keep one version |
| Unwanted navigation | `openUrl` bound to resolve without a tap | No callback, a host allowlist, or no `openUrl` in the catalog |
| Untrusted media | Image / Video / AudioPlayer with an attacker URL (tracking, inappropriate content) | Leave them out of the catalog, or replace them with components that allowlist hosts |
| Resource exhaustion | Huge payloads, deep trees, many surfaces | Size limit before decoding, `maxDepth`, app-side caps |
| Phishing UI | A surface that imitates a login or payment screen | Never collect credentials or payment details in agent-built surfaces; use app-owned screens |
| Data exfiltration | `sendDataModel` surfaces or action contexts carrying sensitive data | No secrets in data models; the server checks what it receives |
| Forged actions | A request that claims an action the user did not take | The server authorises every action; client checks are UX only |
| Code execution | — | Not possible by design: no `eval`, no dynamic code; keep it that way |

## Required controls

### 1. The catalog is the allowlist (mandatory)

The processor only creates surfaces for catalogs it was constructed with and only accepts components and functions those catalogs declare (once validation is on, below). Never build widgets from agent JSON outside a catalog.

Tested: a `createSurface` naming an unregistered catalog throws and renders nothing; the host shows an error state.

### 2. Turn validation on (mandatory for untrusted agents)

`MessageProcessor` runs **without** a validation config by default. In that mode a component type the catalog does not declare is accepted at processing time and renders nothing (tested). Pass a config:

```dart
import 'dart:convert';

import 'package:a2ui_core/a2ui_core.dart';
import 'package:a2ui_flutter/a2ui_flutter.dart';
import 'package:a2ui_flutter/v0_9/basic_catalog.dart';

/// Only these hosts may be opened by the basic catalog's `openUrl` function.
const Set<String> allowedLinkHosts = {'example.com', 'help.example.com'};

/// A processor for an agent you do not fully control.
MessageProcessor<ComponentImplementation> hardenedProcessor({
  required Future<void> Function(Uri url) launch,
}) => MessageProcessor<ComponentImplementation>(
  catalogs: [
    basicCatalog(
      // On v0.9 a bound openUrl call may run without a tap: allowlist it.
      openUrl: (Uri url) async {
        if (url.scheme != 'https' || !allowedLinkHosts.contains(url.host)) {
          throw ArgumentError.value(url, 'url', 'link host not allowed');
        }
        await launch(url);
      },
    ),
  ],
  defaultVersion: A2uiProtocolVersion.v0_9,
  // Whole-surface payloads: every graph check on, unknown types rejected,
  // and only the four v0.9 agent messages accepted.
  validationConfig: const ValidationConfig(
    maxDepth: 20,
    allowedMessages: [
      'createSurface',
      'updateComponents',
      'updateDataModel',
      'deleteSurface',
    ],
  ),
);
```

| `ValidationConfig` field | Default | Use |
|---|---|---|
| `allowUnknownElements` | `false` | Keep false: unknown components (and, below v1.0, functions) are rejected |
| `allowOrphanComponents`, `allowDanglingReferences`, `allowMissingRoot` | `false` | Graph checks; turn on only for surfaces streamed across payloads |
| `allowedMessages` | all | Limit to the four v0.9 agent messages |
| `maxDepth` | 50 | Deepest component chain a surface may declare |
| `targetVersion`, `rootId` | null | Pin the version; change the root id |

`ValidationConfig.strict` is every check on. **`ValidationConfig.relaxed` also sets `allowUnknownElements: true`**, so do not use it for an untrusted agent. For a surface that arrives across several payloads (parent before child), turn off only the checks that wait on later messages:

```dart
/// For a surface streamed across several payloads: the graph checks that
/// wait on later messages are off, unknown components and functions are still
/// rejected. (`ValidationConfig.relaxed` also allows unknown elements.)
const ValidationConfig streamingValidation = ValidationConfig(
  allowOrphanComponents: true,
  allowDanglingReferences: true,
  allowMissingRoot: true,
  maxDepth: 20,
);
```

Tested: this config accepts a parent sent before its child; `ValidationConfig.strict` rejects the same split (control); an unknown component type is still rejected. Schema checks (required properties, types) run in every mode.

### 3. `openUrl` (mandatory decision)

- Without an `openUrl:` callback the function fails: links are off. This is the safe default.
- `a2ui_core` already rejects `javascript:`, `file:` and relative URLs and passes only `http`, `https`, `mailto` and `tel`.
- On v0.9 a bound `openUrl` call runs **whenever it resolves**, so with a callback the agent can open a URL without the user acting. Pass a callback only for an agent you trust, and allowlist scheme and host inside it as above (the callback compiles; its host check is app code, not package behaviour).
- Or remove the function from the catalog (next section).

### 4. Locked-down catalog for untrusted agents

```dart
/// A v0.9 catalog without network media or links: no Image, Video,
/// AudioPlayer or Modal, and no `openUrl` function.
final CatalogImplementation lockedDownCatalog = CatalogImplementation(
  id: 'https://example.com/app/v0_9/locked.json',
  components: [
    BasicComponents.text,
    BasicComponents.row,
    BasicComponents.column,
    BasicComponents.card,
    BasicComponents.list,
    BasicComponents.divider,
    BasicComponents.icon,
    BasicComponents.button,
    BasicComponents.textField,
    BasicComponents.checkBox,
    BasicComponents.choicePicker,
    BasicComponents.slider,
    BasicComponents.dateTimeInput,
  ],
  functions: [
    for (final function in BasicCatalog.v0_9().functions.values)
      if (function.name != 'openUrl') function,
  ],
  themeSchema: BasicComponents.api.themeSchema,
  definitions: BasicComponents.api.definitions,
);
```

Tested with `ValidationConfig.strict`: Text renders; an `Image` is rejected; a Button whose action is an `openUrl` function call is rejected, and the same payload is accepted against the full basic catalog (positive control). The basic Image, Video and AudioPlayer load any `http`/`https` URL, which is why they are omitted.

### 5. Payload size limits (mandatory)

The processor bounds depth, not bytes. Reject oversized input before `jsonDecode`:

```dart
/// Rejects a raw payload larger than [maxBytes] before it is decoded.
Object? decodeBounded(String raw, {int maxBytes = 256 * 1024}) {
  if (utf8.encode(raw).length > maxBytes) {
    throw const FormatException('A2UI payload too large');
  }
  return jsonDecode(raw);
}
```

The SSE and JSONL readers in `genui-a2ui-transport.md` apply the same limit per event or line. Also cap, in the app: surfaces per conversation (delete the oldest or refuse new ones) and components per surface (count `updateComponents` entries). Pick limits from real payloads plus headroom; 256 KiB per event is a starting point, not a measured value.

### 6. Actions are requests, not commands

- Check `action.name` against the app's own allowlist before doing anything locally (camera, navigation, purchase).
- Send the action to the server, which authorises it for the signed-in user. The `context` values are agent-defined and user-editable: validate them server-side.
- Never put tokens, passwords or secrets in a data model or action context; `sendDataModel` surfaces send their whole model to the agent.

### 7. No code execution (absolute)

No `eval`, isolates spawned from agent strings, `Function.apply` on agent-named handlers, or WebViews loading agent HTML. Everything the agent can do is in the catalog.

## Error surfacing

A rejected payload throws `A2uiError` with `code` and `message`. Log both (never the full payload if it may hold user data), show the user that the assistant's response could not be displayed, and keep earlier surfaces. Never catch and continue silently.

## Server-side (agent) checks

Before streaming, the agent server should validate its own output against the catalogs the app advertised. A Dart server can use `a2ui_agent` (`A2uiRequestProcessor.parseResponse`, or the top-level `validatePayload` for one payload), which checks messages against the negotiated catalogs. Python/ADK servers: validate against the catalog JSON schema. Rate-limit per user and per conversation, and cap payload size on the server too.

## Security checklist

- [ ] Packages pinned: `a2ui_flutter: 0.4.0`, `a2ui_core: 0.8.0`
- [ ] `defaultVersion: A2uiProtocolVersion.v0_9`; one version end to end
- [ ] `validationConfig` set; `allowUnknownElements` false; `ValidationConfig.relaxed` not used for untrusted agents
- [ ] Catalog lists only the components and functions the feature needs
- [ ] `openUrl`: no callback, or a scheme + host allowlist, or removed from the catalog
- [ ] Image / Video / AudioPlayer omitted or replaced for untrusted agents
- [ ] Byte limit before `jsonDecode`; surface and component caps
- [ ] `processMessages` wrapped; `A2uiError` logged and shown
- [ ] Action names allowlisted in the app; every action authorised server-side
- [ ] No credentials, payment details or secrets collected in or sent through agent-built surfaces
- [ ] Tests: unregistered catalog, unknown type, oversize payload, locked-down catalog with positive control
