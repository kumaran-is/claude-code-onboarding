---
name: firebase-basics
description: "Firebase CLI foundation for any project. Use when checking the Firebase CLI version, authenticating with Firebase, setting active projects, initializing Firebase services, or running Firebase MCP commands."
metadata:
  triggers: firebase login, firebase use, firebase projects list, firebase init, firebase MCP, Firebase CLI setup, Firebase emulator start
  related-skills: firebase-hosting-basics, deployment-ci-cd
allowed-tools: Bash, Read
---

## Iron Law

**NEVER use the naked `firebase` binary — always `npx -y firebase-tools@<pinned> <cmd>`** (toolkit pin: `15.37.0`, shared with `firebase-hosting-basics`; bump it deliberately after `npm view firebase-tools version`, never `@latest`).

This keeps every developer and CI on the same reviewed CLI version without polluting global node_modules.
Every command in this skill prepends `npx -y firebase-tools@15.37.0`.

## Project Context

Check the project's `CLAUDE.md` to understand which Firebase services are in use and any
project-specific constraints (e.g. which services are intentionally NOT used, whether
Firestore is used as a canonical store or a status bus only, etc.).

Firebase project ID should be stored in an environment variable (e.g. `FIREBASE_PROJECT_ID`)
— never hardcoded.

# Prerequisites

1. **Local Environment Setup:**
   ```bash
   npx -y firebase-tools@15.37.0 --version
   ```
   Requires Node.js (the workspace pins Node 24); `npx` downloads the pinned CLI on first use.

2. **Authentication:**
   ```bash
   npx -y firebase-tools@15.37.0 login
   # Headless / remote shell:
   npx -y firebase-tools@15.37.0 login --no-localhost
   ```

3. **Active Project:**
   ```bash
   npx -y firebase-tools@15.37.0 use
   # Set project from env var (preferred):
   npx -y firebase-tools@15.37.0 use --add ${FIREBASE_PROJECT_ID}
   ```

# Firebase Usage Principles

1. **npx always:** `npx -y firebase-tools@15.37.0 <cmd>` (pinned) — never bare `firebase`, never `@latest`
2. **Consult Firebase MCP first:** Use `developerknowledge_search_documents` before
   falling back to web search or memory
3. **Use Firebase MCP tools for remote API calls:** Crashlytics, Firestore queries,
   project management — always MCP, never manual REST calls
4. **Emulator for local dev:** Set `FIREBASE_AUTH_EMULATOR_HOST` and related emulator
   environment variables — without them, Admin SDK calls hit production Firebase with
   dev tokens

# References

- **Initialize services and CLI commands:** `npx -y firebase-tools@15.37.0 init --help` and
  `npx -y firebase-tools@15.37.0 <command> --help` (the pinned CLI's own help is the source of truth)
- **Service documentation:** Firebase MCP `developerknowledge_search_documents`
- **Hosting deploys, previews, rollback:** `firebase-hosting-basics` skill

# Related Skills

- `flutter-mobile` — Firebase Auth integration in Flutter apps
- `firebase-hosting-basics` — deploy static SPA to Firebase Hosting
- `security-reviewer` — Firestore Security Rules audit
