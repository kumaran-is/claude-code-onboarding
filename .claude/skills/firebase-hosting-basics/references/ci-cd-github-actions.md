# GitHub Actions → Firebase Hosting with Workload Identity Federation

No service-account JSON keys. The workflow exchanges the GitHub OIDC token for short-lived Google credentials via
`google-github-actions/auth` and runs the pinned CLI. Action SHAs resolved with `gh api` on 2026-11-22; the
`firebase-tools` flags were checked with `--help` on 15.37.0. The workflow itself was not executed here (needs a real
project + WIF pool) — run it on a test project first.

```yaml
name: web-deploy
on:
  pull_request:
  push:
    branches: [develop]
permissions:
  contents: read
  id-token: write          # OIDC token for WIF
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.event_name == 'push' && 'production' || 'preview' }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1        # v7.0.1
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1      # v7.1.0
        with: { node-version-file: .nvmrc, cache: npm }
      - run: npm ci
      - run: npx ng build
      - run: npm audit --audit-level=high
      - uses: google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093  # v3.0.0
        with:
          workload_identity_provider: ${{ vars.WIF_PROVIDER }}
          service_account: ${{ vars.DEPLOY_SERVICE_ACCOUNT }}
      - name: Deploy preview
        if: github.event_name == 'pull_request'
        run: npx -y firebase-tools@15.37.0 hosting:channel:deploy "pr-${{ github.event.number }}" --expires 7d --project "${{ vars.FIREBASE_PROJECT_ID }}"
      - name: Deploy live
        if: github.event_name == 'push'
        run: npx -y firebase-tools@15.37.0 deploy --only hosting --project "${{ vars.FIREBASE_PROJECT_ID }}"
      - name: Post-deploy header check
        if: github.event_name == 'push'
        run: node scripts/check-headers.mjs "https://${{ vars.FIREBASE_PROJECT_ID }}.web.app/"
```

- Fork PRs do not get `id-token: write` secrets; previews for forks need a separate, reviewed path.
- The deploy service account gets only the Firebase Hosting Admin role on the project, and the WIF provider is
  restricted by `attribute.repository` (and branch for production) — see `gcp-cloud-run` for the pool setup.
- `scripts/check-headers.mjs`: `deployment-ci-cd/reference/web-frontend-delivery.md` § Post-deploy header check.
- Never run `firebase login:ci` tokens or commit `GOOGLE_APPLICATION_CREDENTIALS` key files.
