---
name: angular-new-app
description: "Official Angular team new-app guidance (angular.dev/ai/agent-skills), vendored as reference. Do not follow its install/ng new steps here: in this repo a new Angular app is created only by /scaffold-angular-app, which applies the same CLI-first steps with a pinned @angular/cli 22.3.0 (no global install, no @latest), the UI-mode question and the verification gates; block-raw-scaffold.sh blocks raw ng new."
license: MIT
compatibility: Requires node, npm, and access to the internet
disable-model-invocation: true
user-invocable: false
source: "official (angular/skills branch 22.3.x, commit 5902a18, build 1002d09 = angular.dev v22.3.0; MIT). Body vendored unchanged except one house-override note at the top; frontmatter adapted for this repo (description scope, source, last-reviewed, triggers)"
last-reviewed: "2026-11-24"
metadata:
  author: Angular Team @ Google
  version: '1.0'
  upstream-version-label: "22.3.x"
  triggers: angular-new-app, official Angular new app skill
---

# Angular New App

> **House override (this repo):** do not run these steps directly. `/scaffold-angular-app` applies them with a pinned CLI (no global install, no `@latest`, no raw `ng new`, which `block-raw-scaffold.sh` blocks) plus the UI-mode question and verification.

You are an expert in TypeScript, Angular, and scalable web application development. You write functional, maintainable, performant, and accessible code following Angular and TypeScript best practices. You have access to tools to create new Angular apps.

When creating a new Angular application for a user, always follow the following steps:

1. **Check for the Angular CLI**: Confirm that the Angular CLI is present before continuing. Here are some ways to confirm:
   - on `*nix` systems `which ng`
   - on Windows systems `where ng`, if powershell `gcm ng`

   If it is present, skip to step 2, if not, ask the user if they'd like to install it globally for the user with the following command:

   `npm install -g @angular/cli`

   _IMPORTANT_: There are best practices available for building outstanding Angular applications via the MCP server that is bundled with the Angular CLI. Available through `ng mcp` and the `get_best_practices`.

2. **Create the new application**: To create the application either suggest a name based on the user prompt or ask the user the name of the application. Create the application with the following command:

   `npx ng new <app-name> [list of flags based on the description of the app] --interactive=false --ai-config=[agents, claude, copilot, cursor, gemini, jetbrains, none, windsurf]`

   _Important_: Prefer agent for `--ai-config`, or use the option that best suits the environment, for example if the user is using Gemini, use `--ai-config=gemini`.

   Load the contents of that AI configuration into memory so that you can refer to it when generating code for the user. This will help you generate code that is consistent with modern Angular best practices.

   Consider these commonly useful flags based on the user's requirements:
   - `--style=scss|css|less` — stylesheet format
   - `--routing` — add routing module
   - `--ssr` — enable server-side rendering
   - `--prefix=<prefix>` — component selector prefix
   - `--skip-tests` — only if the user explicitly requests it

3. Do not start the app until you've built some features, ask the user if they want to start the app. You can always run `npx ng build` to check for errors and repair them.

4. Remember the following guidelines for continuing to generate Angular application code:
   - To generate components, use the Angular CLI `npx ng generate component <component-name>`
   - To generate services, use the Angular CLI `npx ng generate service <service-name>`
   - To generate pipes, use the Angular CLI `npx ng generate pipe <pipe-name>`
   - To generate directives, use the Angular CLI `npx ng generate directive <directive-name>`
   - To generate interfaces, use the Angular CLI `npx ng generate interface <interface-name>`
   - To generate guards, use the Angular CLI `npx ng generate guard <guard-name>`
   - To generate interceptors, use the Angular CLI `npx ng generate interceptor <interceptor-name>`
   - To generate resolvers, use the Angular CLI `npx ng generate resolver <resolver-name>`
   - To generate enums, use the Angular CLI `npx ng generate enum <enum-name>`
   - To generate classes, use the Angular CLI `npx ng generate class <class-name>`

   _IMPORTANT_: Take note of the path returned from running the generate commands so that you know exactly where the new files are.

   Use the Angular CLI to generate the code, then augment the code to meet the needs of the application.

5. To add tailwind, run `npx ng add tailwindcss`. After that, you do not have to do anything else, you can start using tailwind classes in your Angular application. Follow the best practices for tailwind v4 here, learn more if needed: https://tailwindcss.com/docs/upgrade-guide.

_IMPORTANT_: There are best practices available for building outstanding Angular applications via the MCP server that is bundled with the Angular CLI. Available through `npx ng mcp` and the `get_best_practices`.
