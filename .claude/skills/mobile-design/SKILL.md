---
name: mobile-design
description: Mobile-first design doctrine for Flutter (iOS + Android). Load BEFORE flutter-mobile to apply touch psychology, MFRI risk scoring, platform conventions, and performance doctrine before writing any UI code.
allowed-tools: Read
metadata:
  triggers: mobile design, touch psychology, thumb zone, mobile UX, touch targets, platform conventions, mobile performance, MFRI, mobile feasibility, mobile first, iOS design, Android design
  related-skills: flutter-mobile, riverpod-patterns, ui-standards-tokens
  domain: frontend
  role: specialist
  scope: design
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law

**NO FLUTTER UI WITHOUT COMPLETING THE MOBILE CHECKPOINT FIRST — load `reference/touch-psychology.md` and `reference/mobile-performance.md` before writing any screen**

# Mobile Design Skill

**(Mobile-First · Touch-First · Platform-Respectful)**

> **Philosophy:** Touch-first. Battery-conscious. Platform-respectful. Offline-capable.
> **Core Law:** Mobile is NOT a small desktop.
> **Operating Rule:** Think constraints first, aesthetics second.

This skill provides the **design thinking layer** that must be loaded BEFORE `flutter-mobile`. It exists to prevent desktop-thinking, AI-defaults, and unsafe assumptions when designing Flutter screens for iOS and Android.

Load this skill first. Complete the Mobile Checkpoint. Then open `flutter-mobile` to implement.

---

## Mobile Feasibility & Risk Index (MFRI)

Before designing or implementing any mobile feature or screen, assess feasibility.

### MFRI Dimensions (1-5)

| Dimension | Question |
|-----------|----------|
| **Platform Clarity** | Is the target platform (iOS / Android / both) explicitly defined? |
| **Interaction Complexity** | How complex are gestures, flows, or navigation? |
| **Performance Risk** | Does this involve lists, animations, heavy state, or media? |
| **Offline Dependence** | Does the feature break or degrade without network? |
| **Accessibility Risk** | Does this impact motor, visual, or cognitive accessibility? |

### Score Formula

```
MFRI = (Platform Clarity + Accessibility Readiness)
       - (Interaction Complexity + Performance Risk + Offline Dependence)
```

**Range:** `-10 to +10`

### Interpretation

| MFRI | Meaning | Required Action |
|------|---------|-----------------|
| **6-10** | Safe | Proceed normally |
| **3-5** | Moderate | Add performance + UX validation |
| **0-2** | Risky | Simplify interactions or architecture |
| **< 0** | Dangerous | Redesign before implementation |

---

## Mandatory Thinking Before Any Work

### STOP: Ask Before Assuming

If any of the following are not explicitly stated, you MUST ask before proceeding:

| Aspect | Question | Why |
|--------|----------|-----|
| Platform | iOS, Android, or both? | Affects navigation, gestures, typography |
| Framework | Flutter (this workspace is Flutter-only) | Determines performance and patterns |
| Navigation | Tabs, stack, drawer? | Core UX architecture |
| Offline | Must it work offline? | Data and sync strategy |
| Devices | Phone only or tablet too? | Layout and density rules |
| Audience | Consumer, enterprise, accessibility needs? | Touch and readability |

**Flutter note:** This workspace uses Flutter 3.50.x (Dart 3.14) exclusively; Material widgets come from `package:material_ui` (pinned 1.11.1), not the deprecated `package:flutter/material.dart`. Framework is not a question — it is Flutter. If the request is for React Native, redirect to the mobile-developer skill.

Never default to your favorite stack or pattern.

---

## Reference Reading Order

Read these files in this order before designing any screen:

| File | Purpose | When |
|------|---------|------|
| `reference/touch-psychology.md` | Fitts' Law, thumb zones, gesture psychology | Always first |
| `reference/mobile-performance.md` | Flutter const widgets, Riverpod selectors, 60fps | Before any list or animation |
| `reference/platform-ios.md` | iOS HIG, SF Pro, Dynamic Type | When building iOS-specific UI |
| `reference/platform-android.md` | Material 3, Roboto, dp system | When building Android-specific UI |
| `reference/mobile-backend.md` | Offline sync, push notifications, Firebase | When feature uses network |
| `reference/mobile-testing.md` | Device testing, E2E flows, flutter_test | Before writing tests |
| `reference/mobile-debugging.md` | Flutter DevTools, Dart Observatory, xcodebuild MCP | When debugging |
| `reference/flutter-native-capabilities.md` | Camera, media, location, maps, files, PDF, speech, sharing: verified plugin pins, Android/iOS floors, permission keys | Before adding any device-capability plugin |

If you have not read `touch-psychology.md`, you are not allowed to design any UI.

---

## Hard Bans (Flutter-Specific)

### Performance Sins

| Never | Why | Always |
|-------|-----|--------|
| `ListView(children: items.map(...).toList())` | Renders all items, memory explosion | `ListView.builder` or `SliverList` |
| `SingleChildScrollView` wrapping long lists | Same problem as above | `ListView.builder` |
| `setState` for complex cross-widget state | Rebuilds entire subtree | Riverpod providers |
| Heavy computation inside `build()` | Blocks UI thread, drops frames | Offload to isolates or services |
| Non-const constructors on static widgets | Forces unnecessary rebuilds | `const` on every eligible widget |

### Touch and UX Sins

| Never | Why | Always |
|-------|-----|--------|
| Touch targets below 48dp | Missed taps, user frustration | `SizedBox` padding to min 48dp |
| Gesture-only actions with no button | Excludes users | Provide visible button alternative |
| No loading state on async actions | Feels broken | Show CircularProgressIndicator |
| No error recovery | Dead end | Retry button + error message |
| Ignore platform conventions | Breaks muscle memory | iOS edge swipe, Android system back |

### Design Token Sins

| Never | Why | Always |
|-------|-----|--------|
| `Colors.blue` or `Color(0xFF...)` | Hardcoded, breaks theming | `Theme.of(context).colorScheme.*` |
| `EdgeInsets.all(16)` inline | Magic numbers, no token | `AppSpacing.*` tokens |
| `TextStyle(fontSize: 17)` inline | Bypasses type scale | `Theme.of(context).textTheme.*` |

### Security Sins

| Never | Why | Always |
|-------|-----|--------|
| Tokens in SharedPreferences | Easily read without root | `flutter_secure_storage` (Keychain/Keystore) |
| Hardcoded API secrets | Reverse-engineered from APK/IPA | Environment config + secure storage |
| No certificate pinning | MITM risk | Cert pinning via `http_certificate_pinning` |
| Log sensitive data | PII leakage | Never log tokens, passwords, PII |

---

## Platform Unification Matrix

Some elements should be unified across platforms. Others must diverge.

```
UNIFY                          DIVERGE
----------------------         -------------------------
Business logic                 Navigation behavior
Data models                    Gestures
API contracts                  Icons
Validation                     Typography
Error semantics                Pickers / dialogs
```

### Platform Defaults

| Element | iOS | Android |
|---------|-----|---------|
| Font | SF Pro | Roboto |
| Min touch | 44pt | 48dp |
| Back | Edge swipe | System back |
| Sheets | Bottom sheet | Dialog / sheet |
| Icons | SF Symbols | Material Icons |

In Flutter, use `CupertinoWidget` variants for iOS-specific elements and `Material` widgets for Android. For cross-platform, prefer Material with iOS adaptations via `Platform.isIOS` checks or `adaptive` constructors where available.

---

## Mobile Checkpoint

Complete this before writing any widget code. If you cannot fill it in, go back and read the reference files.

```
MOBILE CHECKPOINT
Platform:     [ ] iOS  [ ] Android  [ ] Both
Framework:    Flutter 3.50.x (material_ui)
Files Read:   [ ] touch-psychology  [ ] mobile-performance  [ ] platform-specific
MFRI Score:   ___  (must be >= 3)

3 Principles I Will Apply:
1.
2.
3.

Anti-Patterns I Will Avoid:
1.
2.
```

MFRI score < 3: stop and redesign before opening `flutter-mobile`.

---

## Integration with Workspace

1. Load this skill BEFORE `flutter-mobile`
2. Complete the Mobile Checkpoint above
3. Once checkpoint is done and MFRI >= 3, open `flutter-mobile` for implementation patterns
4. After writing code, dispatch: `riverpod-reviewer`, `flutter-security-expert`, `accessibility-auditor`

### Related Agents

| Agent | When |
|-------|------|
| `riverpod-reviewer` | After writing any provider or state |
| `flutter-security-expert` | After adding auth, storage, or network code |
| `accessibility-auditor` | After building any screen or interactive widget |

---

## Related Skills

- `flutter-mobile` — Implementation patterns, templates, codegen
- `riverpod-patterns` — Provider types, AsyncValue, select()
- `ui-standards-tokens` — AppSpacing, colorScheme, textTheme tokens

---

> **Final Law:**
> Mobile users are distracted, interrupted, and impatient — often using one hand on a bad network with low battery.
> **Design for that reality, or your app will fail quietly.**
