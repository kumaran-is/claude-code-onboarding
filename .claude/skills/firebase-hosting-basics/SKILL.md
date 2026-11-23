---
name: firebase-hosting-basics
description: "Firebase Hosting for static SPAs and web apps. Use when configuring the firebase.json hosting block (rewrites, security headers, cache rules), deploying a static site, creating preview channels for PR review, promoting or rolling back a release, or setting up GitHub Actions CI/CD with Workload Identity Federation. Do NOT use for Firebase App Hosting (SSR)."
metadata:
  triggers: firebase hosting, deploy angular spa, firebase hosting deploy, preview channel, hosting clone, rollback, static site deploy, firebase ci/cd, hosting rewrite, hosting headers
  related-skills: deployment-ci-cd, firebase-basics, gcp-cloud-run, angular-spa
last-reviewed: "2026-11-22"
allowed-tools: Bash, Read, Write, Edit, Glob
---

## Iron Law

**NO FIREBASE HOSTING DEPLOY WITHOUT WORKLOAD IDENTITY FEDERATION.**

CI/CD uses GitHub Actions + WIF — never long-lived service account JSON keys. The
`GOOGLE_APPLICATION_CREDENTIALS` environment variable must never point to a key file
in any workflow or `.env` file.

## Project Context

Before using this skill:
- Check `CLAUDE.md` for the project's build tool and output path (e.g. `dist/`)
- Confirm the `firebase.json` location (typically repo root)
- Confirm whether a `hosting` block already exists in `firebase.json`

Build the web app before deploying:
```bash
# Adjust command to match your project's build setup
npm run build
# Confirm the output directory matches firebase.json "public" setting
```

# What are you doing?

**Configuring firebase.json?**
→ Load [references/configuration.md](references/configuration.md)
→ Set `"public"` to the project's actual build output directory

**Deploying live or to a preview channel?**
→ Load [references/deploying.md](references/deploying.md)
→ For CI/CD with GitHub Actions: Load [references/ci-cd-github-actions.md](references/ci-cd-github-actions.md)

**Adding env vars for project ID or WIF?**
→ Must sync across all env files (`.env`, `.env.staging`, `.env.production`) in the SAME PR
→ Run the project's env-sync check before committing

# References

Pin the CLI everywhere: `npx -y firebase-tools@15.37.0` (no `@latest`).


- **Configuration:** [references/configuration.md](references/configuration.md)
- **Deploying:** [references/deploying.md](references/deploying.md)
- **CI/CD (GitHub Actions + WIF):** [references/ci-cd-github-actions.md](references/ci-cd-github-actions.md)

# Related Skills

- `angular-spa` — Angular build setup; produces the static output
- `firebase-basics` — Firebase CLI auth, project setup, npx discipline
- `gcp-cloud-run` — WIF setup patterns reused for Firebase Hosting CI/CD
- `deployment-engineer` agent — for complex multi-environment pipeline setup
- `deployment-ci-cd/reference/web-frontend-delivery.md` — runtime config, cache policy, post-deploy header check, rollback

# Local Development

Two different things — use both:
```bash
# Day-to-day development: the framework dev server (no Firebase involved)
npm run start

# Production build served by the Hosting emulator: applies firebase.json rewrites and headers
npx ng build
npx -y firebase-tools@15.37.0 emulators:start --only hosting
# Port = emulators.hosting.port in firebase.json (5000 if unset)
```
The emulator proves rewrites, headers and cache rules (verified on 15.37.0); it does not prove CDN caching or the
custom-domain certificate — check the live URL after deploy.
