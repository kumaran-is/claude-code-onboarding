# Mobile Testing Patterns

Flutter-specific testing strategy: when to use each testing approach and why. Mobile testing is NOT web testing — different constraints, different strategies.

**Tools in this workspace:** `flutter_test` (unit + widget), `integration_test` (integration), Maestro MCP (E2E cross-platform), xcodebuild MCP (iOS build and launch). See the `flutter-mobile` skill for detailed tool setup. Mobile UI/E2E automation never uses browser tools (Playwright, Chrome DevTools); missing Maestro/device = BLOCKED/NOT RUN (`.claude/rules/testing-tool-selection.md`).

---

## Mobile Testing Mindset

```
Mobile testing differs from web:
+-- Real devices matter (emulators hide bugs)
+-- Platform differences (iOS vs Android behavior)
+-- Network conditions vary wildly
+-- Battery/performance under test
+-- App lifecycle (background, killed, restored)
+-- Permissions and system dialogs
+-- Touch interactions vs clicks
```

---

## AI Mobile Testing Anti-Patterns

| AI Default | Why It's Wrong | Flutter-Correct |
|------------|----------------|-----------------|
| Web-based testing patterns | Misses native layer | flutter_test + E2E on device |
| Mock everything in widget tests | Misses integration bugs | Test with ProviderScope overrides |
| Browser-based E2E | Cannot test native features | Maestro MCP or Detox |
| Skip platform-specific tests | iOS/Android behavior differs | Test both platforms |
| Skip performance tests | Mobile perf is critical | Profile on low-end device |
| Test only happy path | Mobile has more edge cases | Offline, permissions, interrupts |
| 100% unit test coverage goal | False security | Pyramid balance |
| Same patterns as web testing | Different environment | Flutter-specific tools |

---

## 1. Testing Tool Selection

### Decision Tree

```
WHAT ARE YOU TESTING?
        |
        +-- Pure functions, utilities, helpers
        |   -> flutter_test unit tests
        |   -> No widget or Flutter setup needed
        |
        +-- Individual widgets (isolated)
        |   -> flutter_test widget tests
        |   -> testWidgets() + WidgetTester
        |
        +-- Widgets with providers, navigation, state
        |   -> flutter_test with ProviderScope overrides
        |   -> Mocktail for mocking repositories
        |
        +-- Full user flows (login, checkout, etc.)
        |   -> Maestro MCP (cross-platform, YAML-based)
        |   -> Save flows to test/e2e/
        |
        +-- Performance, memory, paint timing
            -> Flutter DevTools (profile mode)
            -> xcodebuild MCP for iOS profiling
            -> flutter run --profile on real device
```

### Tool Comparison

| Tool | Platform | Speed | Reliability | Use When |
|------|----------|-------|-------------|----------|
| **flutter_test** | Flutter | Fast | High | Unit and widget tests |
| **integration_test** | Flutter | Medium | High | Full app integration |
| **Maestro MCP** | Both | Medium | Medium | E2E cross-platform flows |
| **xcodebuild MCP** | iOS | Medium | High | iOS build + UI test |

---

## 2. Testing Pyramid for Flutter

```
               +-----------+
               |   E2E     |  10%
               |  Maestro  |  Slow, expensive, essential
               +-----------+
               | Integration|  20%
               |   Tests    |  flutter_test with ProviderScope
               +-----------+
               |  Widget    |  30%
               |   Tests    |  Isolated widget testing
               +-----------+
               |   Unit     |  40%
               |   Tests    |  Pure Dart logic
               +-----------+
```

### Why This Distribution?

| Level | Why This % |
|-------|------------|
| **E2E 10%** | Slow, but catches integration bugs across layers |
| **Integration 20%** | Tests real user flows without full app launch |
| **Widget 30%** | Fast feedback on UI changes and states |
| **Unit 40%** | Fastest, most stable, logic coverage |

If you have 90% unit tests and 0% E2E tests, you are testing the wrong things.

---

## 3. What to Test at Each Level

### Unit Tests (flutter_test)

```
TEST:
+-- Utility functions (formatDate, calculatePrice)
+-- Domain entities and value objects
+-- Repository methods (with mocked data sources)
+-- Riverpod notifier state transitions
+-- Validation logic
+-- Business rules

DO NOT TEST:
+-- Widget rendering (use widget tests)
+-- Navigation (use integration tests)
+-- Firebase SDK internals (mock the repository)
+-- Third-party library internals
```

```dart
// Example: unit test for a notifier
void main() {
  test('counter increments', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    expect(container.read(counterProvider), 0);
    container.read(counterProvider.notifier).increment();
    expect(container.read(counterProvider), 1);
  });
}
```

### Widget Tests (flutter_test)

```
TEST:
+-- Widget renders correctly given state
+-- User interactions (tap, type, swipe)
+-- Loading / error / empty states
+-- Semantics labels exist
+-- Provider state displayed correctly

DO NOT TEST:
+-- Internal implementation details
+-- Snapshot everything (only key screens)
+-- Styling specifics (brittle)
+-- Third-party widget internals
```

```dart
// Example: widget test with Riverpod
void main() {
  testWidgets('shows loading indicator', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          myProvider.overrideWith((ref) => const AsyncLoading()),
        ],
        child: const MaterialApp(home: MyScreen()),
      ),
    );

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
```

### Integration Tests

```
TEST:
+-- Form submission flows
+-- Navigation between screens
+-- State persistence across screens
+-- Provider integration with mocked repositories
+-- Firestore reads/writes (with emulator or mocks)

DO NOT TEST:
+-- Every possible path (use unit tests)
+-- Live Firebase (use emulator or mocks)
+-- Backend logic (backend tests)
```

### E2E Tests with Maestro MCP

```
TEST:
+-- Critical user journeys (login, signup, purchase)
+-- Offline -> online transitions
+-- Deep link handling
+-- Push notification navigation
+-- Permission flows (camera, notifications)

DO NOT TEST:
+-- Every edge case (too slow and brittle)
+-- Visual regression (use golden tests instead)
+-- Non-critical features
+-- Backend-only logic
```

**Workflow with Maestro MCP:**

```
1. Build and launch app:
   - iOS: xcodebuild MCP build_run_sim
   - Android: flutter run
2. Describe the test flow in natural language to Claude
3. Claude generates YAML via Maestro MCP and runs it
4. Claude reports pass/fail per step
5. Save generated YAML to test/e2e/<flow-name>.yaml for reuse
```

> Flow conventions (tags, helpers, regex matching, iOS/Android differences, evidence), the `integration_test` vs Maestro split,
> and simulator push/deep-link testing: `flutter-mobile/reference/flutter-e2e-maestro.md`.
> Flaky-test protocol and false-red triage: `flutter-mobile/reference/flutter-testing-traps.md` §9.

**Flow file conventions:**
- Save to `test/e2e/` at project root
- Name by user journey: `login-flow.yaml`, `create-item-flow.yaml`
- Use `appId` matching your bundle ID (`com.company.app`)
- One flow per file — keep flows focused

---

## 4. Platform-Specific Testing

### What Differs Between iOS and Android

| Area | iOS Behavior | Android Behavior | Test Both? |
|------|--------------|------------------|------------|
| **Back navigation** | Edge swipe | System back button | Yes |
| **Permissions** | Ask once, settings | Ask each time | Yes |
| **Keyboard** | Different appearance | Different behavior | Yes |
| **Push format** | APNs payload | FCM payload | Yes |
| **Deep links** | Universal Links | App Links | Yes |
| **Gestures** | CupertinoWidget specific | Material gestures | When using adaptive widgets |

### Platform Testing Strategy

```
FOR EACH PLATFORM:
+-- Run unit tests (identical on both)
+-- Run widget tests (identical on both)
+-- Run E2E with Maestro on iOS simulator (xcodebuild MCP)
+-- Run E2E with Maestro on Android emulator (flutter run)
+-- Test platform-specific features separately
```

---

## 5. Offline and Network Testing

### Offline Scenarios to Test

| Scenario | What to Verify |
|----------|----------------|
| Start app offline | Shows Firestore cached data or offline indicator |
| Go offline mid-action | Action queued locally, not lost |
| Come back online | Firestore syncs queued writes, no duplicates |
| Slow network (2G) | Loading states visible, no timeout crash |
| Firestore permission denied | Error state shown, not silent failure |

### How to Test Network Conditions

```
UNIT TESTS:
+-- Mock the repository layer with mocktail
+-- Return NetworkException to test error states

WIDGET TESTS:
+-- Override providers to return AsyncError
+-- Verify error widget appears with retry button

E2E WITH MAESTRO:
+-- Use Maestro network conditions if supported
+-- Or manually put device in airplane mode mid-test

MANUAL:
+-- Use iOS Network Link Conditioner (developer tools)
+-- Android Studio emulator network throttling
```

---

## 6. Performance Testing

### What to Measure

| Metric | Target | Flutter Tool |
|--------|--------|--------------|
| **App startup** | < 2 seconds | `flutter run --trace-startup` |
| **Screen transition** | < 300ms | DevTools Timeline |
| **List scroll** | 60 FPS | DevTools + manual feel |
| **Memory** | Stable, no leaks | DevTools Memory tab |
| **Widget rebuilds** | Minimal | DevTools Widget Inspector |

### When to Performance Test

```
PERFORMANCE TEST:
+-- Before release (required)
+-- After adding list screens or animations
+-- After upgrading major dependencies
+-- When users report slowness

WHERE TO TEST:
+-- Real device (REQUIRED)
+-- Low-end Android (Galaxy A series, ~$200 phone)
+-- Older iOS device (iPhone SE 2nd gen or iPhone 8)
+-- NOT on emulator (lies about performance)
+-- With production-like data (not 3 test items)

FLUTTER PROFILE MODE:
flutter run --profile
// Then open Flutter DevTools for analysis
```

---

## 7. Accessibility Testing

### What to Verify

| Element | Check |
|---------|-------|
| Interactive elements | Have Semantics label |
| Images | Have Semantics label or `excludeSemantics: true` |
| Form inputs | Labels linked via Semantics |
| Buttons | role = button in Semantics |
| Touch targets | >= 44x44 (iOS) / 48x48dp (Android) |
| Color contrast | WCAG AA minimum (4.5:1 text, 3:1 large) |

### How to Test

```
AUTOMATED (in widget tests):
await tester.pumpWidget(myWidget);
// getSemantics(finder) returns the nearest ANCESTOR semantics node, which can be a merged node.
// Locate by label (also detects duplicate nodes) and read flags via flagsCollection:
final node = find.bySemanticsLabel('Save button');
expect(node, findsOneWidget);
expect(tester.getSemantics(node).flagsCollection.isButton, isTrue);
// hasFlag is deprecated (after Flutter 3.32). Details: flutter-mobile/reference/flutter-testing-traps.md §4

MANUAL:
+-- Enable VoiceOver (iOS): Settings -> Accessibility -> VoiceOver
+-- Enable TalkBack (Android): Settings -> Accessibility -> TalkBack
+-- Navigate entire app with screen reader only
+-- Test with increased text size (max scale)
+-- Test with reduced motion setting
```

---

## 8. CI/CD Integration (GitHub Actions)

This workspace uses GitHub Actions exclusively.

### What to Run Where

| Stage | Tests | Devices |
|-------|-------|---------|
| **PR** | Unit + Widget | None (fast, no device needed) |
| **Merge to main** | + Integration | iOS Simulator (via GitHub Actions macOS runner) |
| **Pre-release** | + E2E | Real devices or Firebase Test Lab |
| **Nightly** | Full suite | Device farm |

### GitHub Actions Example

```yaml
# .github/workflows/flutter-test.yml
name: Flutter Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with:
          flutter-version: '3.41.0'
      - run: flutter pub get
      - run: flutter test
      - run: flutter analyze
```

---

## Mobile Testing Checklist

### Before PR

- [ ] Unit tests for new business logic
- [ ] Widget tests for new UI components (loading, error, data states)
- [ ] No `print()` statements in tests
- [ ] Tests pass on CI: `flutter test`
- [ ] `flutter analyze` clean

### Before Release

- [ ] E2E flow tested on iOS simulator (Maestro MCP)
- [ ] E2E flow tested on Android emulator (Maestro MCP)
- [ ] Tested on low-end device in profile mode
- [ ] Offline scenarios verified (airplane mode test)
- [ ] Performance acceptable (60fps scroll, <2s startup)
- [ ] Accessibility verified (VoiceOver + TalkBack)

### What to Skip (Consciously)

- 100% coverage target (aim for meaningful coverage of business logic)
- Snapshot tests for every widget (use sparingly for key screens)
- Third-party library internals
- Backend logic (covered by backend tests)

---

## Testing Questions to Ask

Before writing tests, answer:

1. **What could break?** -> Test that
2. **What is critical for users?** -> E2E test that
3. **What is complex logic?** -> Unit test that
4. **What is platform-specific?** -> Test on both iOS and Android
5. **What happens offline?** -> Test that scenario with Firestore offline mode

> **Remember:** Good mobile testing is about testing the RIGHT things, not EVERYTHING. A flaky E2E test is worse than no test. A failing unit test that catches a regression is worth 100 passing trivial tests.
