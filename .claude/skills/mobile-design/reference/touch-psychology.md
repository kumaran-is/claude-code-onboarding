# Touch Psychology Reference

Deep dive into mobile touch interaction, Fitts' Law for touch, thumb zone anatomy, gesture psychology, and haptic feedback. This is the mobile equivalent of ux-psychology — critical for all Flutter UI work.

**Flutter note:** All principles here apply directly to Flutter. Flutter widgets respect platform touch conventions by default. Use `GestureDetector`, `InkWell`, and `Semantics` to apply these patterns correctly.

---

## 1. Fitts' Law for Touch

### The Fundamental Difference

```
DESKTOP (Mouse/Trackpad):
+-- Cursor size: 1 pixel (precision)
+-- Visual feedback: Hover states
+-- Error cost: Low (easy to retry)
+-- Target acquisition: Fast, precise

MOBILE (Finger):
+-- Contact area: ~7mm diameter (imprecise)
+-- Visual feedback: No hover, only tap
+-- Error cost: High (frustrating retries)
+-- Occlusion: Finger covers the target
+-- Target acquisition: Slower, needs larger targets
```

### Fitts' Law Formula Adapted

```
Touch acquisition time = a + b x log2(1 + D/W)

Where:
+-- D = Distance to target
+-- W = Width of target
+-- For touch: W must be MUCH larger than desktop
```

### Minimum Touch Target Sizes

| Platform | Minimum | Recommended | Use For |
|----------|---------|-------------|---------|
| **iOS (HIG)** | 44pt x 44pt | 48pt+ | All tappable elements |
| **Android (Material)** | 48dp x 48dp | 56dp+ | All tappable elements |
| **WCAG 2.2 AA (2.5.8)** | 24 x 24 CSS px (or 24 px spacing) | 44 x 44 (2.5.5, AAA) | Legal/accessibility floor; platform minimums above are stricter |
| **Critical Actions** | - | 56-64px | Primary CTAs, destructive actions |

### Visual Size vs Hit Area

```
+-------------------------------------+
|                                     |
|    +-------------------------+      |
|    |                         |      |
|    |    [  BUTTON  ]         | <- Visual: 36px
|    |                         |      |
|    +-------------------------+      |
|                                     | <- Hit area: 48px (padding extends)
+-------------------------------------+

OK: Visual can be smaller if hit area is minimum 44-48px
WRONG: Making hit area same as small visual element
```

**Flutter implementation:**

```dart
// Correct: Extend hit area with GestureDetector + SizedBox
GestureDetector(
  onTap: onTap,
  child: SizedBox(
    width: 48,
    height: 48,
    child: Icon(Icons.close, size: 24), // Small visual, large hit area
  ),
)

// Or use InkWell with minimum padding
InkWell(
  onTap: onTap,
  child: Padding(
    padding: const EdgeInsets.all(12), // Extends hit area
    child: Icon(Icons.close, size: 24),
  ),
)
```

### Application Rules

| Element | Visual Size | Hit Area |
|---------|-------------|----------|
| Icon buttons | 24-32px | 44-48px (padding) |
| Text links | Any | 44px height minimum |
| List items | Full width | 48-56px height |
| Checkboxes/Radio | 20-24px | 44-48px tap area |
| Close/X buttons | 24px | 44px minimum |
| Tab bar items | Icon 24-28px | Full tab width, 49px height (iOS) |

---

## 2. Thumb Zone Anatomy

### One-Handed Phone Usage

```
Research shows: 49% of users hold phone one-handed.

+-------------------------------------+
|                                     |
|  +-----------------------------+    |
|  |       HARD TO REACH         |    | <- Status bar, top nav
|  |      (requires stretch)     |    |    Put: Back, menu, settings
|  |                             |    |
|  +-----------------------------+    |
|  |                             |    |
|  |       OK TO REACH           |    | <- Content area
|  |      (comfortable)          |    |    Put: Secondary actions, content
|  |                             |    |
|  +-----------------------------+    |
|  |                             |    |
|  |       EASY TO REACH         |    | <- Tab bar, FAB zone
|  |      (thumb's arc)          |    |    Put: PRIMARY CTAs!
|  |                             |    |
|  +-----------------------------+    |
|                                     |
|          [    HOME    ]             |
+-------------------------------------+
```

### Placement Guidelines

| Element Type | Ideal Position | Reason |
|--------------|----------------|--------|
| **Primary CTA** | Bottom center/right | Easy thumb reach |
| **Tab bar** | Bottom | Natural thumb position |
| **FAB** | Bottom right | Easy for right hand |
| **Navigation** | Top (stretch) | Less frequent use |
| **Destructive actions** | Top left | Hard to reach = harder to accidentally tap |
| **Dismiss/Cancel** | Top left | Convention + safety |
| **Confirm/Done** | Top right or bottom | Convention |

### Large Phone Considerations (>6")

On large phones, the top 40% becomes a "dead zone" for one-handed use.

Solutions:
- Bottom sheet navigation instead of top drawers
- Floating action buttons in bottom-right quadrant
- Pull-down interfaces that bring content within reach
- Gesture-based alternatives to top actions

---

## 3. Touch vs Click Psychology

### Expectation Differences

| Aspect | Click (Desktop) | Touch (Mobile) |
|--------|-----------------|----------------|
| **Feedback timing** | Can wait 100ms | Expect instant (<50ms) |
| **Visual feedback** | Hover then Click | Immediate tap response |
| **Error tolerance** | Easy retry | Frustrating, feels broken |
| **Precision** | High | Low |
| **Context menu** | Right-click | Long press |
| **Cancel action** | ESC key | Swipe away, outside tap |

### Touch Feedback Requirements

```
Tap -> Immediate visual change (< 50ms)
+-- Highlight state (background color change)
+-- Scale down slightly (0.95-0.98)
+-- Ripple effect (Android Material / InkWell)
+-- Haptic feedback for confirmation
+-- Never nothing!

Loading -> Show within 100ms
+-- If action takes > 100ms
+-- Show CircularProgressIndicator
+-- Disable button (prevent double tap)
+-- Optimistic UI when possible
```

**Flutter implementation:**

```dart
// InkWell provides ripple (Material) automatically
InkWell(
  onTap: () {
    HapticFeedback.lightImpact(); // Haptic on tap
    setState(() => _loading = true);
  },
  child: ...,
)

// Scale animation on press
GestureDetector(
  onTapDown: (_) => setState(() => _pressed = true),
  onTapUp: (_) => setState(() => _pressed = false),
  child: AnimatedScale(
    scale: _pressed ? 0.96 : 1.0,
    duration: const Duration(milliseconds: 80),
    child: ...,
  ),
)
```

---

## 4. Gesture Psychology

### Gesture Discoverability Problem

```
Problem: Gestures are INVISIBLE.
+-- User must discover/remember them
+-- No hover/visual hint
+-- Different mental model than tap
+-- Many users never discover gestures

Solution: Always provide visible alternative
+-- Swipe to delete -> Also show delete button or menu
+-- Pull to refresh -> Also show refresh button
+-- Pinch to zoom -> Also show zoom controls
+-- Gestures as shortcuts, not only way
```

### Common Gesture Conventions

| Gesture | Universal Meaning | Usage |
|---------|-------------------|-------|
| **Tap** | Select, activate | Primary action |
| **Double tap** | Zoom in, like/favorite | Quick action |
| **Long press** | Context menu, selection mode | Secondary options |
| **Swipe horizontal** | Navigation, delete, actions | List actions |
| **Swipe down** | Refresh, dismiss | Pull to refresh |
| **Pinch** | Zoom in/out | Maps, images |

### Platform Gesture Differences

| Gesture | iOS | Android |
|---------|-----|---------|
| **Back** | Edge swipe from left | System back button/gesture |
| **Share** | Action sheet | Share sheet |
| **Context menu** | Long press | Long press |
| **Dismiss modal** | Swipe down | Back button or swipe |
| **Delete in list** | Swipe left, tap delete | Swipe left, immediate or undo |

---

## 5. Haptic Feedback Patterns

### Why Haptics Matter

```
Haptics provide:
+-- Confirmation without looking
+-- Richer, more premium feel
+-- Accessibility (blind users)
+-- Reduced error rate
+-- Emotional satisfaction

Without haptics:
+-- Feels "cheap" or web-like
+-- User unsure if action registered
+-- Missed opportunity for delight
```

### Flutter Haptic API

```dart
import 'package:flutter/services.dart';

// Light impact: selection changes, toggles, minor actions
HapticFeedback.selectionClick();

// Light impact: minor confirmations
HapticFeedback.lightImpact();

// Medium impact: standard tap confirmation
HapticFeedback.mediumImpact();

// Heavy impact: important completed, destructive action
HapticFeedback.heavyImpact();

// Vibrate: error state (use sparingly)
HapticFeedback.vibrate();
```

### Haptic Usage Guidelines

```
USE haptics for:
+-- Button taps on primary CTAs
+-- Toggle switches changing state
+-- Pull to refresh trigger point
+-- Successful action completion
+-- Errors and warnings
+-- Swipe action thresholds

DO NOT use haptics for:
+-- Every scroll position
+-- Every list item render
+-- Background events
+-- Passive displays
+-- Too frequently (haptic fatigue)
```

### Haptic Intensity Mapping

| Action Importance | Flutter Call | Example |
|-------------------|--------------|---------|
| Minor/Browsing | `selectionClick()` | Scrolling picker |
| Standard Action | `lightImpact()` | Toggle, minor tap |
| Significant Action | `mediumImpact()` | Confirm, complete |
| Critical/Destructive | `heavyImpact()` | Delete, payment |
| Error | `vibrate()` | Failed action |

---

## 6. Mobile Cognitive Load

### How Mobile Differs from Desktop

| Factor | Desktop | Mobile | Implication |
|--------|---------|--------|-------------|
| **Attention** | Focused sessions | Interrupted constantly | Design for micro-sessions |
| **Context** | Controlled environment | Anywhere, any condition | Handle bad lighting, noise |
| **Multitasking** | Multiple windows | One app visible | Complete task in-app |
| **Input speed** | Fast (keyboard) | Slow (touch typing) | Minimize input, smart defaults |
| **Error recovery** | Easy (undo, back) | Harder | Prevent errors, easy recovery |

### Reducing Mobile Cognitive Load

```
1. ONE PRIMARY ACTION per screen
   -> Clear what to do next

2. PROGRESSIVE DISCLOSURE
   -> Show only what's needed now

3. SMART DEFAULTS
   -> Pre-fill what you can

4. CHUNKING
   -> Break long forms into steps

5. RECOGNITION over RECALL
   -> Show options, don't make user remember

6. CONTEXT PERSISTENCE
   -> Save state on interrupt/background
```

### Miller's Law for Mobile

```
Desktop: 7+-2 items in working memory
Mobile: Reduce to 5+-1 (more distractions)

Navigation: Max 5 tab bar items
Options: Max 5 per menu level
Steps: Max 5 visible steps in progress
```

---

## 7. Touch Accessibility

### Motor Impairment Considerations

Users with motor impairments may have tremors, use assistive devices, have limited reach, need more time, or make accidental touches.

Design responses:
- Generous touch targets (48dp+ in Flutter)
- Adjustable timing for gestures
- Undo for destructive actions
- Switch access support via `Semantics`
- Voice control support via semantic labels

### WCAG 2.2 Touch Targets

- **2.5.8 Target Size (Minimum), AA:** ≥ 24 × 24 CSS px, or spaced so a 24 px circle centred on each target does not overlap another.
- **2.5.5 Target Size (Enhanced), AAA:** ≥ 44 × 44 CSS px.
- Platform guidelines are stricter and are what Flutter tests assert: 48 × 48 dp Android (`androidTapTargetGuideline`), 44 × 44 pt iOS (`iOSTapTargetGuideline`).
- Canonical policy: `.claude/skills/accessibility-audit/reference/wcag22-checklist.md` §1.

### Accessible Touch Patterns

| Pattern | Accessible Implementation |
|---------|---------------------------|
| Swipe actions | Provide menu alternative |
| Drag and drop | Provide select + move option |
| Pinch zoom | Provide zoom buttons |
| Long press menus | Provide icon button with same options |
| Shake gesture | Provide button alternative |

---

## 8. The Premium Feel

```
What makes touch feel "premium":
+-- Instant response (< 50ms)
+-- Appropriate haptic feedback
+-- Smooth 60fps animations
+-- Correct resistance/physics
+-- Spring physics on dismiss

Emotional touch feedback:
+-- Success: haptic + confetti or checkmark animation
+-- Error: haptic + shake animation
+-- Warning: haptic + attention color
+-- Delight: unexpected smooth micro-animation
```

---

## 9. Touch Psychology Checklist

### Before Every Screen

- [ ] All touch targets >= 44-48dp?
- [ ] Primary CTA in thumb zone (bottom)?
- [ ] Destructive actions require confirmation?
- [ ] Gesture alternatives exist (visible buttons)?
- [ ] Haptic feedback on important actions?
- [ ] Immediate visual feedback on tap?
- [ ] Loading states for actions > 100ms?

### Before Release

- [ ] Tested on smallest supported device?
- [ ] Tested one-handed on large phone?
- [ ] All gestures have visible alternatives?
- [ ] Haptics work correctly (test on physical device)?
- [ ] Touch targets tested with accessibility settings?
- [ ] No tiny close buttons or icon-only actions?

---

## 10. Quick Reference

```
Touch Target Sizes
                  iOS        Android     WCAG 2.2 AA (AAA)
Minimum:        44pt       48dp       24px (44px)
Recommended:    48pt+      56dp+      -
Spacing:        8pt+       8dp+       8px+

Thumb Zone
TOP:      Navigation, settings, back (infrequent)
MIDDLE:   Content, secondary actions
BOTTOM:   Primary CTA, tab bar, FAB (frequent)

Flutter Haptics
selectionClick():  Selection, picker
lightImpact():     Minor actions, toggles
mediumImpact():    Standard tap confirmation
heavyImpact():     Confirm, complete, destructive
vibrate():         Error state
```

---

> **Remember:** Every touch is a conversation between user and device. Make it feel natural, responsive, and respectful of human fingers — not precise cursor points.
