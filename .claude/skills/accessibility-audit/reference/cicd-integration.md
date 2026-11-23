# CI/CD Accessibility Integration

GitHub Actions workflows for automated accessibility testing. Add to existing pipelines — do not create a standalone workflow unless the project has no existing CI.

## Angular — Add to Existing CI Pipeline

Add these steps to your existing Angular GitHub Actions workflow (after `ng build`):

```yaml
# In your existing .github/workflows/ci.yml — add these steps after build

      - name: Start Angular dev server for a11y scan
        run: npx ng serve --configuration=production &
        working-directory: ./frontend  # adjust to your Angular app path

      - name: Wait for Angular server
        run: npx wait-on http://localhost:4200 --timeout 60000

      - name: Run axe accessibility scan
        run: npm run test:a11y
        working-directory: ./frontend
        # Requires: package.json script "test:a11y": "playwright test e2e/a11y.spec.ts"
        # The spec uses .withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']) (angular-a11y-automated.md §1)

      - name: Run pa11y-ci scan
        run: npx pa11y-ci --config .pa11yci.json
        working-directory: ./frontend

      - name: Upload a11y report
        uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: a11y-report-${{ github.run_number }}
          path: frontend/a11y-report/
          retention-days: 14

      - name: Stop Angular server
        if: always()
        run: kill $(lsof -t -i:4200) || true
```

**Required package.json scripts:**
```json
{
  "scripts": {
    "test:a11y": "playwright test e2e/a11y.spec.ts --reporter=html --output=a11y-report"
  }
}
```

**Required .pa11yci.json** (Angular routes to audit):
```json
{
  "defaults": {
    "standard": "WCAG2AA",
    "runners": ["axe"],
    "threshold": 0,
    "timeout": 30000,
    "wait": 2000
  },
  "urls": [
    "http://localhost:4200",
    "http://localhost:4200/orders",
    "http://localhost:4200/dashboard"
  ]
}
```

## Flutter — Add to Existing CI Pipeline

Add these steps to your existing Flutter GitHub Actions workflow:

```yaml
# In your existing .github/workflows/flutter-ci.yml — add these steps

      - name: Run accessibility widget tests
        run: flutter test test/accessibility/ --reporter=expanded

      - name: Run integration accessibility tests (Android emulator)
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 33
          script: |
            flutter drive \
              --driver=test_driver/integration_test.dart \
              --target=integration_test/a11y_test.dart \
              -d emulator-5554

      - name: Upload accessibility test results
        uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: flutter-a11y-results-${{ github.run_number }}
          path: test/accessibility/
          retention-days: 14
```

## Standalone Accessibility Workflow (Optional)

Only create this if the project has no existing CI. Otherwise, add to existing workflow above.

```yaml
# .github/workflows/accessibility.yml
name: Accessibility Audit

on:
  pull_request:
    paths:
      - 'frontend/src/**'
      - 'lib/**'  # Flutter source

jobs:
  a11y-angular:
    runs-on: ubuntu-latest
    if: contains(github.event.pull_request.changed_files, 'frontend/')
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: ./frontend

      - name: Build Angular app
        run: npx ng build --configuration=production
        working-directory: ./frontend

      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium
        working-directory: ./frontend

      - name: Start server and run axe scan
        run: |
          npx ng serve --configuration=production &
          npx wait-on http://localhost:4200 --timeout 60000
          npm run test:a11y
        working-directory: ./frontend

      - name: Run pa11y-ci
        run: npx pa11y-ci --config .pa11yci.json
        working-directory: ./frontend

      - name: Upload report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: angular-a11y-report
          path: frontend/a11y-report/
          retention-days: 14

  a11y-flutter:
    runs-on: ubuntu-latest
    if: contains(github.event.pull_request.changed_files, 'lib/')
    steps:
      - uses: actions/checkout@v4

      - name: Setup Flutter
        uses: subosito/flutter-action@v2
        with:
          flutter-version: '3.41.0'
          channel: 'stable'

      - name: Install dependencies
        run: flutter pub get

      - name: Run accessibility widget tests
        run: flutter test test/accessibility/ --reporter=expanded

      - name: Analyze (catches semantic issues)
        run: flutter analyze
```

## Gate: Fail PR on Any Violation

Both jobs use `--threshold 0` (pa11y) and `expect(results.violations).toEqual([])` (axe): any automated violation fails the PR.

**Do not merge PRs with automated accessibility failures.** A green gate means "no automated violations" only. It is not WCAG 2.2 AA conformance: the manual checks in `wcag22-checklist.md` §4 are still required and are recorded as PASS / FAIL / NOT RUN.
