# Deploying to Firebase Hosting

All commands use the pinned CLI: `npx -y firebase-tools@15.37.0 …` (flags checked with `--help` on 15.37.0,
2026-11-22). Pin the same version in CI and bump it deliberately.

```bash
npm ci && npx ng build                                    # production is the default configuration
npx -y firebase-tools@15.37.0 emulators:start --only hosting   # serve dist locally with firebase.json headers/rewrites
npx -y firebase-tools@15.37.0 hosting:channel:deploy pr-123 --expires 7d   # preview channel (max 30d)
npx -y firebase-tools@15.37.0 deploy --only hosting       # live channel
```

- **Preview channels** get their own URL and expire. They are public URLs: never point them at production data
  with write access, and add `X-Robots-Tag: noindex`. The CLI syncs preview domains to Firebase Auth authorized
  domains by default; pass `--no-authorized-domains` when the app does not use Firebase Auth. Every OAuth provider
  needs the preview redirect URI registered separately.
- **Promote, don't rebuild:** `hosting:clone <site>:<channel> <site>:live` copies the exact tested version to live.
- **Rollback:** Firebase console → Hosting → release history → *Rollback*, or re-clone the previous good version
  (`hosting:clone <site>@<versionId> <site>:live`). Rollback is instant because `index.html` is `no-cache` and old
  hashed assets are still in the previous version.
- Before upload, validate `public/config.json` with the same parser the app uses and refuse a production config that
  names `localhost` or an emulator host (`deployment-ci-cd/reference/web-frontend-delivery.md` §2).
- After every deploy run the post-deploy header check (`deployment-ci-cd/reference/web-frontend-delivery.md`); a
  failing check means roll back.
- Firebase Hosting has no gradual traffic split for static content; "canary" = a preview channel validated with
  smoke tests, then clone to live. Use Firebase App Hosting or Cloud Run when you need percentage rollout (UNVERIFIED
  for App Hosting — check its docs before relying on it).
