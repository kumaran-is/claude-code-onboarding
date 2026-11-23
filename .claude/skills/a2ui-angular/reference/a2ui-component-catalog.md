# A2UI Component Catalog Reference

## Overview

This catalog defines the component types an A2UI renderer must support. Each component type has a fixed property schema. Agents request these types by name; the renderer validates the type against this catalog (allowlist) and maps it to a native Angular/daisyUI component.

In v0.8 (legacy, the shapes in this file) all text fields use typed value objects: `{"literalString": "value"}` for static text or `{"path": "/json/pointer"}` for reactive data binding. The combined form `{"path": "/...", "literalString": "default"}` binds to the path and falls back to the literal when the path is absent. Plain strings are not valid for text fields.

---

## Official Component Types (v0.8, legacy)

> v0.9 basic catalog (`@a2ui/web_core@0.15.0` `src/v0_9/schemas/catalogs/basic/catalog.json`): `Text`, `Image`, `Icon`, `Video`, `AudioPlayer`, `Row`, `Column`, `List`, `Card`, `Tabs`, `Modal`, `Divider`, `Button`, `TextField`, `CheckBox`, `ChoicePicker`, `Slider`, `DateTimeInput`. Property shapes below are v0.8; in v0.9 the type is a string field (`"component": "Text"`) and properties sit beside it (`"text": "Hi"`).

### Layout Components

#### `Row`

Horizontal arrangement of child components.

```json
{
  "id": "action-row",
  "component": {
    "type": "Row",
    "children": {"explicitList": ["btn-cancel", "btn-confirm"]},
    "alignment": "end"
  }
}
```

| Property | Type | Values |
|----------|------|--------|
| `children` | children object | `{"explicitList": ["id1", "id2"]}` or `{"template": {"dataBinding": "/path", "componentId": "tpl"}}` |
| `alignment` | string | `center`, `start`, `end` |

**Angular/daisyUI mapping:** `<div class="flex flex-row">`

---

#### `Column`

Vertical arrangement of child components.

```json
{
  "id": "page-column",
  "component": {
    "type": "Column",
    "children": {"explicitList": ["card-1", "btn-book"]},
    "alignment": "start"
  }
}
```

| Property | Type | Values |
|----------|------|--------|
| `children` | children object | `{"explicitList": ["id1", "id2"]}` or `{"template": {"dataBinding": "/path", "componentId": "tpl"}}` |
| `alignment` | string | `center`, `start`, `end` |

**Angular/daisyUI mapping:** `<div class="flex flex-col">`

---

### Display Components

#### `Text`

Text content block with optional usage hint for semantic styling.

```json
{
  "id": "price-label",
  "component": {
    "type": "Text",
    "literalString": "Price includes breakfast and Wi-Fi",
    "usageHint": "body"
  }
}
```

Data binding example — content from reactive data model:

```json
{
  "id": "checkin-date",
  "component": {
    "type": "Text",
    "path": "/reservation/date",
    "usageHint": "body"
  }
}
```

| Field | Type | Values |
|-------|------|--------|
| `literalString` | string | Static text value |
| `path` | string | JSON Pointer into the reactive data model |
| `usageHint` | string | `h1`, `h2`, `h3`, `h4`, `h5`, `h6`, `body` |

**Angular/daisyUI mapping:** `<p>`, `<h1>`–`<h6>` based on `usageHint`

---

#### `Image`

Standalone image with URL and optional sizing.

```json
{
  "id": "hotel-photo",
  "component": {
    "type": "Image",
    "url": {"literalString": "https://example.com/hotel.jpg"}
  }
}
```

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `url` | value object | Yes | Image URL — `{"literalString": "..."}` or `{"path": "/..."}` |

**Angular/daisyUI mapping:** `<img>` with `alt` attribute enforced

---

#### `Icon`

Material Icon or custom icon set glyph.

```json
{
  "id": "flight-icon",
  "component": {
    "type": "Icon",
    "name": {"literalString": "flight_takeoff"}
  }
}
```

| Property | Type | Description |
|----------|------|-------------|
| `name` | value object | Icon identifier — `{"literalString": "..."}` (Material Icons name or custom set key) |

**Angular/daisyUI mapping:** `<mat-icon>` or custom icon component

---

#### `Divider`

Visual separator between content sections.

```json
{
  "id": "section-divider",
  "component": {
    "type": "Divider",
    "axis": "horizontal"
  }
}
```

| Property | Type | Values |
|----------|------|--------|
| `axis` | string | `horizontal`, `vertical` |

**Angular/daisyUI mapping:** `<div class="divider">`

---

### Interactive Components

#### `Button`

Clickable element that triggers an action. The button's visible content is a separate component referenced by `child`.

```json
{
  "id": "btn-book",
  "component": {
    "type": "Button",
    "child": "btn-book-label",
    "primary": true,
    "action": {
      "name": "book_hotel",
      "context": [
        {"key": "hotelId", "value": {"literalString": "H-456"}},
        {"key": "checkIn", "value": {"path": "/reservation/date"}}
      ]
    }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `child` | string | Yes | Component ID of the button's content/label component |
| `action.name` | string | Yes | Action identifier sent to agent |
| `action.context` | array | No | Key-value pairs providing data to the agent |
| `primary` | boolean | No | Whether to apply primary/prominent styling |

**Angular/daisyUI mapping:** `<button class="btn btn-primary">`

---

#### `TextField`

Text input for user data collection. Supports bidirectional data binding via `text`.

```json
{
  "id": "destination-input",
  "component": {
    "type": "TextField",
    "label": {"literalString": "Destination"},
    "text": {"path": "/search/destination"},
    "textFieldType": "shortText"
  }
}
```

| Property | Type | Values |
|----------|------|--------|
| `label` | value object | Display label — `{"literalString": "..."}` or `{"path": "/..."}` |
| `text` | value object | `{"path": "/..."}` — bidirectional binding; reads initial value and writes user input back |
| `textFieldType` | string | `shortText` (default), `longText`, `email` |

**Angular/daisyUI mapping:** `<input class="input">` (daisyUI 5: bordered by default)

---

#### `Checkbox`

Boolean toggle with bidirectional data model binding.

```json
{
  "id": "breakfast-check",
  "component": {
    "type": "Checkbox",
    "label": {"literalString": "Include breakfast"},
    "value": {"path": "/reservation/includeBreakfast"}
  }
}
```

| Property | Type | Description |
|----------|------|-------------|
| `label` | value object | Checkbox label text — `{"literalString": "..."}` or `{"path": "/..."}` |
| `value` | value object | `{"path": "/..."}` — reads initial boolean state and writes user toggle back |

**Angular/daisyUI mapping:** `<input type="checkbox" class="checkbox">`

---

#### `DateTimeInput`

Date and/or time selection input with bidirectional data binding.

```json
{
  "id": "checkin-input",
  "component": {
    "type": "DateTimeInput",
    "value": {"path": "/reservation/checkIn"},
    "enableDate": true,
    "enableTime": false
  }
}
```

| Property | Type | Description |
|----------|------|-------------|
| `value` | value object | `{"path": "/..."}` — reads and writes the selected date/time value |
| `enableDate` | boolean | Show date picker (default: `true`) |
| `enableTime` | boolean | Show time picker (default: `false`) |

**Angular/daisyUI mapping:** `<input type="date">` / `<input type="datetime-local">` wrapped in a labelled field group

---

> Container components (Card, Modal, Tabs, List), extended catalog, and how to extend are in `a2ui-component-containers.md`.
