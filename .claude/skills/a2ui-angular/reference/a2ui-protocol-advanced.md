# A2UI Protocol — Action Model, Streaming, and A2A Integration

> **LEGACY v0.8 payloads.** The JSON and backend snippets in this file use v0.8 shapes (`surfaceUpdate`,
> `beginRendering`, `literalString`, `userAction`). The backend rules (bypass the LLM for search results,
> action context limited to what the user selected, never an empty agent turn) apply unchanged to v0.9. For v0.9
> message shapes, actions and streaming lifecycle use the `genui-contract` skill
> (`../../genui-contract/reference/catalog-contract.md`, `../../genui-contract/reference/runtime-lifecycle.md`).

## Action Model

Actions are declared on interactive components (e.g., Button). When a user triggers the action, the renderer resolves any `{"path": "..."}` references against the current data model and sends a `userAction` message to the agent.

```json
{
  "action": {
    "name": "confirm_booking",
    "context": [
      {"key": "details", "value": {"path": "/reservation"}},
      {"key": "userId", "value": {"literalString": "u-123"}}
    ]
  }
}
```

### Action Context Fields

| Field | Description |
|-------|-------------|
| `name` | Action identifier — sent to the agent to identify which action was triggered |
| `context` | Array of key-value pairs providing data to the agent |
| `context[].key` | Named parameter for the agent |
| `context[].value` | Either `{"literalString": "..."}` for a static value or `{"path": "/..."}` for a reactive data model reference |

### Action Flow

```
User clicks "Book Now" button
    |
Renderer extracts action name + context from component definition
    |
Resolves any {"path": "..."} references against current data model
    |
userAction message sent to agent (same transport channel)
    |
Agent processes action and returns new A2UI JSONL payload
    |
Renderer applies surfaceUpdate / dataModelUpdate messages
```

---

## Streaming Protocol

A2UI uses **JSONL** (newline-delimited JSON) — one complete JSON message per line. This enables incremental rendering without buffering a full response.

| Transport | Format | Use Case |
|-----------|--------|----------|
| **SSE** (Server-Sent Events) | Each event data = one JSONL line | Simple, HTTP-based, auto-reconnect |
| **WebSocket** | Each message = one JSONL line | Bidirectional, actions sent on same connection |
| **REST** | Full response = multiple JSONL lines | Simplest, no streaming |
| **A2A** (Agent-to-Agent) | A2UI embedded in A2A messages | Multi-agent orchestration |

### JSONL Streaming Example

Each line is a complete, independently parseable JSON message:

```
{"surfaceUpdate":{"surfaceId":"main","components":[{"id":"root","component":{"type":"Column","children":{"explicitList":["card-1"]}}},{"id":"card-1","component":{"type":"Card","child":"text-1"}},{"id":"text-1","component":{"type":"Text","literalString":"Loading..."}}]}}
{"dataModelUpdate":{"surfaceId":"main","contents":[{"key":"price","valueString":"$450"}]}}
{"surfaceUpdate":{"surfaceId":"main","components":[{"id":"text-1","component":{"type":"Text","path":"/price","usageHint":"body"}}]}}
{"beginRendering":{"surfaceId":"main","root":"root"}}
```

A `surfaceUpdate` with a component ID that already exists replaces the previous version — this enables progressive updates as the agent streams more detail.

---

## A2A Integration

A2UI integrates with the Agent-to-Agent (A2A) protocol for multi-agent orchestration scenarios.

| Integration Detail | Value |
|--------------------|-------|
| A2A extension URI | `https://a2ui.org/a2a-extension/a2ui/v0.8` (v0.8; the v0.9 URI is UNVERIFIED, confirm on a2ui.org before use) |
| MIME type | `application/json+a2ui` |

### Agent Card (server advertises capabilities)

```json
{
  "capabilities": {
    "extensions": [{
      "uri": "https://a2ui.org/a2a-extension/a2ui/v0.8",
      "params": {
        "supportedCatalogIds": ["https://example.com/catalog/v1"],
        "acceptsInlineCatalogs": true
      }
    }]
  }
}
```

### A2A Message Metadata (client declares capabilities)

```json
{
  "metadata": {
    "a2uiClientCapabilities": {
      "supportedCatalogIds": ["https://example.com/catalog/v1"],
      "inlineCatalogs": [
        {
          "catalogId": "https://example.com/catalog/v1",
          "components": {},
          "styles": {}
        }
      ]
    }
  }
}
```

### Python ADK Integration

The Python ADK (Google ADK) provides schema manager and validation utilities for A2UI:

- LLM output is validated against the effective catalog before transmission
- The schema manager enforces component property types and required fields
- Unknown component types are rejected at the ADK layer before the client receives them

---

## Versioning

- Renderers should handle unknown properties gracefully (ignore, don't crash)
- Renderers must reject unknown component types (not in catalog)
- The `v0.8` extension URI in A2A messages identifies the protocol version in multi-agent contexts

---

## Gemini Wrapper Normalization (Backend — Required)

Gemini sometimes omits the `surfaceUpdate` outer key, returning the payload one level too shallow. The backend MUST normalize this before streaming to the frontend.

Add this normalization immediately after parsing each JSON object from the agent response:

```python
# Normalize: Gemini sometimes omits the "surfaceUpdate" wrapper
if (
    isinstance(parsed, dict)
    and "surfaceId" in parsed
    and "components" in parsed
    and "surfaceUpdate" not in parsed
):
    parsed = {"surfaceUpdate": parsed}
```

Also add a frontend fallback in `travel-agent.service.ts` `buildSurfaceState()`:

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// Fallback: agent sent surfaceUpdate with a 'root' component but no beginRendering
if (!state.rootComponentId && state.componentMap.has('root')) {
  state.rootComponentId = 'root';
}
```

Never rely on Gemini always outputting the exact wrapper structure — always normalize defensively.

---

## Multi-Object JSON Parsing (Backend — Required)

Gemini may concatenate multiple JSON objects on one line with no separator. Never use `json.loads(line)` on a single line. Instead use `json.JSONDecoder.raw_decode()` to consume objects sequentially:

```python
decoder = json.JSONDecoder()
text = response_text.strip()
pos = 0
while pos < len(text):
    # Skip whitespace
    while pos < len(text) and text[pos] in ' \t\n\r':
        pos += 1
    if pos >= len(text):
        break
    if text[pos] != '{':
        next_brace = text.find('{', pos)
        if next_brace == -1:
            break
        pos = next_brace
        continue
    try:
        parsed, consumed = decoder.raw_decode(text, pos)
        # normalize + yield parsed here
        pos += consumed - pos
    except json.JSONDecodeError:
        pos += 1  # skip bad char and continue
```

This correctly handles:
- Single object per line (normal case)
- Multiple objects concatenated on one line (Gemini quirk)
- Objects split across lines (handled by stripping the full response_text first)

❌ Never do: `for line in response_text.splitlines(): json.loads(line)`

---

## Action Context Must Only Carry What the User Explicitly Selected

Each button's action context must contain only the IDs and values that the user explicitly interacted with on that surface. Never pre-populate context with default values from a different entity.

**The problem:** When a surface shows Entity A results, it is tempting to pre-fill a related Entity B ID as a "convenience default" in the action context. This causes the backend to silently act on Entity B even though the user never selected it.

**Examples across domains:**
- Travel: "Book Room" button carrying a default flight ID → flight booked without user asking
- Fitness: "Log Workout" button carrying a default meal plan ID → plan logged without user choosing
- Rental: "Request Repair" button carrying a default contractor ID → contractor assigned silently
- E-commerce: "Add to Cart" button carrying a default bundle ID → extras added without consent

❌ FORBIDDEN — defaulting to a related entity the user never selected:
```python
# Pre-filling a related entity as a convenience
related_id = related_items[0]["id"] if related_items else ""
context = [
    {"key": "primaryId", "value": {"literalString": primary["id"]}},
    {"key": "relatedId", "value": {"literalString": related_id}},  # user never picked this
]
```

✅ CORRECT — only include what the user explicitly selected on this surface:
```python
context = [
    {"key": "primaryId", "value": {"literalString": primary["id"]}},
    # relatedId omitted — user has not selected one
]
```

In the `/action` handler, treat a missing context key as "not selected" — never fall back to a default:
```python
primary_id = get_context_value(context, "primaryId")
related_id = get_context_value(context, "relatedId")  # may be empty — that is correct

if related_id:
    message = f"Process {primary_id} with related item {related_id}."
else:
    message = f"Process {primary_id} only. No related item selected."
```

The agent instruction must have a distinct response template for each combination (with / without related item), so the confirmation accurately reflects what was actually booked, logged, or submitted.

---

## Each Search Surface Shows Only Its Own Results

A surface builder function is responsible for ONE category of results. Never add results from a different category as "related" or "suggested" content unless the user explicitly requested a combined view.

**The problem:** Cross-populating results creates confusion about what the user is actually acting on, and makes action context ambiguous.

**Examples across domains:**
- Travel: hotel search surface showing flight cards below → user confused about what "Book" does
- Fitness: exercise search surface showing nutrition cards → user unsure what they're logging
- Rental: property search surface showing maintenance history → unrelated to the search intent
- E-commerce: product search surface showing unrelated "frequently bought together" → inflates cart

❌ FORBIDDEN:
```python
def _build_item_results_surface(query):
    components = _build_item_cards(query)
    components += _build_related_category_cards(query)  # user did not ask for this
```

✅ CORRECT — one surface builder, one result category:
```python
def _build_item_results_surface(query):
    components = _build_item_cards(query)
    # nothing else — the surface shows only what was searched
```

If a combined view is genuinely needed (e.g. "package deals"), build a dedicated combined surface triggered by an explicit user action, not appended silently to a single-category search.

---

## Bypass the LLM for All Search Actions (Critical)

Search result surfaces MUST be built deterministically from in-memory data. Never route search actions through the LLM.

❌ FORBIDDEN — routing search through LLM:
```python
# Don't do this for search actions
response = await agent.run(f"Search hotels in {destination}")
```

✅ CORRECT — deterministic surface building:
```python
if action_key == "search_hotels_form":
    destination = get_context_value(context, "destination")
    nights = get_context_value(context, "nights")
    messages = _build_hotel_results_surface(destination, nights)
    return _stream_prebuilt(messages)  # no LLM involved

elif action_key == "search_flights_form":
    messages = _build_flight_results_surface(to_city, from_city, date)
    return _stream_prebuilt(messages)  # no LLM involved
```

Only booking confirmations should go through the LLM. Search results must never be LLM-generated — LLMs hallucinate data, invent prices, and return wrong surface types.

---

## Empty Agent Response — Never Render a Blank Bubble

If the agent returns empty text or produces zero parseable JSON, ALWAYS emit an error surface — never let the frontend show an empty bubble.

```python
# Backend: guard against empty response
if not response_text or not response_text.strip():
    error_surface = _build_error_surface("Agent returned an empty response. Please try again.")
    yield f"data: {json.dumps(error_surface)}\n\n"
    yield f"data: {json.dumps({'beginRendering': {'surfaceId': 'main', 'root': 'root'}})}\n\n"
    return

# Also guard after parsing: if no JSON objects were found
if not found_any:
    error_surface = _build_error_surface(f"Unexpected response: {response_text[:100]}")
    yield f"data: {json.dumps(error_surface)}\n\n"
    yield f"data: {json.dumps({'beginRendering': {'surfaceId': 'main', 'root': 'root'}})}\n\n"
```

The frontend must never show an empty agent turn. An error card is always better than silence.
