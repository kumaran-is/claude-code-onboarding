---
name: mobile-developer
description: Expert mobile developer for React Native, native Swift/SwiftUI, Kotlin/Compose, and mobile CI/CD (Fastlane, Codemagic, Bitrise, EAS). Use for everything mobile that flutter-mobile does NOT cover. For Flutter 3.41.x work, use flutter-mobile skill instead.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
metadata:
  triggers: React Native, React Native New Architecture, Hermes, TurboModules, SwiftUI, Kotlin Compose, Fastlane, Codemagic, Bitrise, EAS Update, CodePush, Detox, native module, brownfield, Expo, MAUI
  related-skills: flutter-mobile, mobile-design
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-03-15"
---

## Iron Law

**FOR FLUTTER WORK — USE `flutter-mobile` SKILL INSTEAD. This skill is for React Native, native Swift/Kotlin, and mobile CI/CD only.**

# Mobile Developer Skill

## Disambiguation — Which Skill to Use

| Task | Use This Skill | Use flutter-mobile Instead |
|------|---------------|---------------------------|
| React Native app | YES | No |
| Flutter screen/provider/widget | No | YES |
| Native Swift/SwiftUI module | YES | No |
| Native Kotlin/Compose module | YES | No |
| Fastlane lanes / Codemagic pipeline | YES | No |
| EAS Update / CodePush OTA | YES | No |
| Flutter CI/CD (GitHub Actions, build) | No — use deployment-engineer agent | No |
| Detox E2E (React Native) | YES | No |
| Maestro E2E (Flutter; never a browser tool, see `.claude/rules/testing-tool-selection.md`) | No | YES (via flutter-mobile) |
| App Store signing (any) | No | No — use asc-signing-setup skill |

## Capabilities

### 1. React Native (RN 0.74+, New Architecture)
New Architecture (Fabric renderer, TurboModules, JSI), Hermes engine, Metro bundler configuration, Flipper debugging, Codegen for typed native modules, and the bridge-free JSI layer for synchronous native calls.

### 2. Expo (SDK 50+)
EAS Build for managed and bare workflows, EAS Update for over-the-air JS bundle delivery, development builds with custom native code, config plugins for extending native projects without ejecting.

### 3. Native Integration
Swift/SwiftUI platform channel implementations (method channels, event channels), Kotlin/Compose native module authoring, brownfield integration (embedding RN screens in an existing native app or vice versa).

### 4. Architecture
Clean Architecture for React Native (data/domain/presentation layers), MVVM with React Query or Zustand, MVI with Redux Toolkit, BLoC pattern adapted for RN, feature-first folder structure mirroring the flutter-mobile convention.

### 5. Performance
App startup time reduction (Hermes bytecode, lazy loading), memory leak detection (Flipper Memory Monitor, Instruments, Android Profiler), battery impact analysis, FlatList/FlashList virtualization, Reanimated 3 for 60fps UI-thread animations, InteractionManager for deferred heavy work.

### 6. Data Management
Realm for complex relational offline data, WatermelonDB for high-performance sync, MMKV for fast key-value storage, offline-first sync patterns with conflict resolution (last-write-wins, CRDT), background sync with WorkManager (Android) and BGTaskScheduler (iOS).

### 7. Mobile CI/CD
Fastlane lanes (match for code signing, gym for builds, pilot/deliver for distribution), Codemagic YAML workflows, Bitrise pipelines, GitHub Actions with mobile-specific caching (CocoaPods, Gradle), CodePush for hotfix OTA, EAS Update for Expo-managed OTA.

### 8. Testing
Jest unit tests with `@testing-library/react-native`, Detox for black-box E2E on device/emulator, Maestro for declarative E2E (RN and native), XCTest for Swift unit tests, Firebase Test Lab and Bitrise device farm for multi-device coverage.

### 9. Security
OWASP MASVS compliance (MASVS-STORAGE, MASVS-CRYPTO, MASVS-NETWORK, MASVS-AUTH), `react-native-keychain` / `expo-secure-store` for credential storage, certificate pinning via `react-native-ssl-pinning` or TrustKit (iOS), RASP (Runtime Application Self-Protection), jailbreak/root detection.

## Quick Reference — React Native Setup

```bash
# New React Native project (Expo recommended for new projects)
npx create-expo-app MyApp --template blank-typescript
cd MyApp

# Core RN dependencies
npx expo install expo-router react-native-screens react-native-safe-area-context

# EAS CLI for builds and OTA
npm install -g eas-cli
eas login
eas build:configure
```

```bash
# Bare React Native (when full native control is required)
npx @react-native-community/cli init MyApp --template react-native-template-typescript
cd MyApp
npx pod-install ios  # Install CocoaPods dependencies
```

```bash
# Run
npx expo start           # Expo dev server
npx react-native run-ios # Bare RN iOS
npx react-native run-android # Bare RN Android

# Detox E2E setup
npm install --save-dev detox @types/detox
npx detox init
```

## Fastlane CI/CD Example

```ruby
# fastlane/Fastfile
default_platform(:ios)

platform :ios do
  lane :beta do
    increment_build_number(
      build_number: ENV["BUILD_NUMBER"]
    )
    match(type: "appstore")
    build_app(scheme: "MyApp", configuration: "Release")
    upload_to_testflight(skip_waiting_for_build_processing: true)
  end

  lane :deploy do
    match(type: "appstore")
    build_app(scheme: "MyApp", configuration: "Release")
    upload_to_app_store(force: true, skip_screenshots: true)
  end
end

platform :android do
  lane :beta do
    gradle(
      task: "bundle",
      build_type: "Release",
      project_dir: "android/"
    )
    upload_to_play_store(track: "internal")
  end

  lane :deploy do
    gradle(task: "bundle", build_type: "Release", project_dir: "android/")
    upload_to_play_store(track: "production", rollout: "0.1")
  end
end
```

## EAS Update (OTA) Example

```bash
# Publish an update to the preview channel
eas update --channel preview --message "Fix checkout crash"

# Promote preview to production
eas update --channel production --message "Stable release"
```

```json
// eas.json
{
  "build": {
    "preview": {
      "distribution": "internal",
      "ios": { "simulator": false }
    },
    "production": {
      "ios": { "buildConfiguration": "Release" },
      "android": { "buildType": "apk" }
    }
  },
  "update": {
    "channel": "production"
  }
}
```

## Documentation Sources

Before generating code, consult these sources for current syntax and APIs:

| Source | Tool | Purpose |
|--------|------|---------|
| React Native | `Context7` MCP | RN APIs, hooks, native modules, New Architecture APIs |
| Expo | `Context7` MCP | EAS, SDK APIs, config plugins, expo-router |
| Swift/SwiftUI | `Context7` MCP | SwiftUI views, Combine, platform integrations |
| Kotlin/Compose | `Context7` MCP | Jetpack Compose, coroutines, platform integrations |
| Fastlane | WebFetch docs.fastlane.tools | Lane actions, match, gym, pilot, deliver |
| Detox | `Context7` MCP | E2E matchers, device API, configuration |

## Hard Prohibitions

- Never use this skill for Flutter UI work — use `flutter-mobile`
- No `AsyncStorage` for sensitive data — use `react-native-keychain` or `expo-secure-store`
- No array index as `key` in FlatList/FlashList — use stable unique IDs
- No inline functions in `renderItem` — use `useCallback` to prevent re-renders
- No JS-thread animations — always use `useNativeDriver: true` or Reanimated 3
- No `console.log` in production — use a structured logger (e.g., `react-native-logs`)
- No raw HTTP without SSL pinning for auth or payment endpoints
- No secrets in JS bundle — use EAS secrets or native keystore

## Post-Code Review

After writing code, dispatch these reviewer agents:
- `code-reviewer` — general quality, DRY, error handling
- `security-reviewer` — OWASP MASVS compliance, secure storage, network security
- `flutter-security-expert` — only if the feature also has a Flutter counterpart that shares native code
