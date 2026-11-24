# SDK Generation and CI/CD Integration

Commands and workflows for generating client SDKs from OpenAPI specs and integrating validation into CI/CD pipelines.

## SDK Generation

### Installation

```bash
npm install -g @openapitools/openapi-generator-cli
```

### TypeScript Client

```bash
openapi-generator-cli generate \
  -i openapi.yaml \
  -g typescript-fetch \
  -o ./generated/ts-client \
  --additional-properties=supportsES6=true,npmName=@myorg/api-client
```

### TypeScript Client with zod 4 Runtime Validation

Use this when the caller must reject a response that drifted from the spec (MCP servers calling a REST upstream, service-to-service calls). Verified 2026-11-23 against an OpenAPI 3.1 document emitted by Fastify + zod (`code-first-patterns.md`), Node 26.13.1, TypeScript 6.0.3 strict (`module`/`moduleResolution: nodenext`), zod 4.6.7.

| Generator | Verdict | Evidence |
|---|---|---|
| `@hey-api/openapi-ts` 0.99.0 (`zod` plugin + `@hey-api/sdk` with `validator: true`) | **Default** | Emits zod 4 forms (`z.uuid()`, `z.int()`, `z.iso.datetime()`), validates the request before sending and the response after receiving; the fetch client is generated into the output folder, so the runtime dependency is only `zod`. `tsc` exit 0; contract tests 4/4 |
| `orval` 8.49.0 (`client: "zod"` + `client: "fetch"`) | Alternative | zod 4 forms; `tsc` exit 0; contract tests 3/3. The fetch client does not validate by itself: parse responses with the generated schemas |
| `openapi-zod-client` 1.18.3 | **Do not use** | Last release 2025-02-10; depends on `zod ^3` and `@zodios/core` (peer `zod ^3`), so installing its runtime next to zod 4 fails with `ERESOLVE`; the `schemas-only` template compiles but emits deprecated zod 3 calls; its nested zod 3.25.76 is flagged by `npm audit` (GHSA-mrhx-c7xc-m3w5) |

```typescript
// openapi-ts.config.ts
import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "./openapi.json",
  output: "./src/generated/orders-api",
  plugins: ["@hey-api/client-fetch", "@hey-api/typescript", "zod", { name: "@hey-api/sdk", validator: true }],
});
```

```json
{
  "devDependencies": { "@hey-api/openapi-ts": "0.99.0" },
  "dependencies": { "zod": "4.6.7" },
  "overrides": { "@hey-api/json-schema-ref-parser": { "js-yaml": "4.3.2" } }
}
```

- Run `npx @hey-api/openapi-ts` with the project's `tsconfig.json` present: it reads `moduleResolution` and writes `.js` import extensions for `nodenext`. Generated without a tsconfig, the output failed `tsc` with 57 errors (TS2834, missing extensions).
- The `overrides` entry is needed while `@hey-api/json-schema-ref-parser` 1.4.4 pins `js-yaml` 4.2.0: without it `npm audit --audit-level=high` exits 1 (three js-yaml advisories); with it the audit exits 0 and the contract tests still pass. Remove it once a release lifts the pin.
- Generated schemas drop `additionalProperties: false`: both generators emit `z.object`, which strips unknown keys instead of rejecting them. Keep strict input validation on the server; the client schema is a drift detector, not a security boundary.
- Generate in CI from the committed spec and fail the job on `git diff --exit-code src/generated`, so a spec change without regeneration is visible.

Contract test (Vitest) against the real server, with a planted drift as the negative control:

```typescript
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { expect, it } from "vitest";
import { createClient } from "./generated/orders-api/client/index.js";
import { createOrder } from "./generated/orders-api/sdk.gen.js";

const body = { customerId: "0b7c4d2e-1f3a-4b5c-9d6e-7f8a9b0c1d2e", sku: "A-1", quantity: 2, couponCode: null };

it("rejects a response that drifted from the spec", async () => {
  const drift = createServer((_req, res) => {
    res.writeHead(201, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: "42", status: "pending", quantity: "2", createdAt: "1970-01-01T00:00:00.000Z" }));
  });
  await new Promise<void>((resolve) => drift.listen(0, "127.0.0.1", resolve));
  const client = createClient({ baseUrl: `http://127.0.0.1:${(drift.address() as AddressInfo).port}` });
  await expect(createOrder({ client, body, throwOnError: true })).rejects.toThrow();
  drift.close();
});
```

*Executed:* the round trip against the real Fastify server returned 201 and passed the response validator; the drift test passed; deleting the generated `responseValidator` made it fail (mutation check); an invalid request body was rejected before any network call.

### Python Client

```bash
openapi-generator-cli generate \
  -i openapi.yaml \
  -g python \
  -o ./generated/python-client \
  --additional-properties=packageName=api_client
```

### Java Client

```bash
openapi-generator-cli generate \
  -i openapi.yaml \
  -g java \
  -o ./generated/java-client \
  --additional-properties=library=webclient,dateLibrary=java8
```

### Common Generator Options

| Generator | Key Properties | Notes |
|-----------|---------------|-------|
| `typescript-fetch` | `supportsES6`, `npmName`, `npmVersion` | Browser + Node.js compatible |
| `typescript-axios` | `npmName`, `withSeparateModelsAndApi` | Axios-based, good for Node.js |
| `python` | `packageName`, `projectName`, `library` | `library`: `urllib3` (default), `asyncio`, `httpx`, `httpx2` (openapi-generator v7.27.0 docs) |
| `python-pydantic-v1` | `packageName` | Pydantic **v1** models: do not use for services on Pydantic 2 |
| `java` | `library`, `dateLibrary`, `groupId` | Libraries: webclient, resttemplate, okhttp-gson |
| `dart-dio` | `pubName`, `pubAuthor` | For Flutter/Dart projects |
| `kotlin` | `library`, `groupId` | Libraries: jvm-okhttp4, jvm-retrofit2 |

### Best Practices for SDK Generation

- Pin the generator version in CI to avoid breaking changes
- Set `operationId` on every endpoint -- generators use it for method names
- Use `$ref` for shared schemas -- produces cleaner generated code
- Include examples in the spec -- some generators use them for documentation
- Run `openapi-generator-cli validate` before generating to catch issues early

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/api-docs.yml
name: API Docs
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Lint OpenAPI spec
        uses: stoplightio/spectral-action@v0.8.10
        with:
          file_glob: "openapi.yaml"

      - name: Build docs
        run: npx @redocly/cli build-docs openapi.yaml -o docs/index.html

      - name: Upload docs
        uses: actions/upload-artifact@v4
        with:
          name: api-docs
          path: docs/
```

### Extended Pipeline (Validate + Generate + Publish)

```yaml
# .github/workflows/api-full.yml
name: API Full Pipeline
on:
  push:
    paths:
      - "openapi.yaml"
      - ".spectral.yaml"

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Lint OpenAPI spec
        uses: stoplightio/spectral-action@v0.8.10
        with:
          file_glob: "openapi.yaml"

  generate-sdk:
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate TypeScript client
        run: |
          npx @openapitools/openapi-generator-cli generate \
            -i openapi.yaml \
            -g typescript-fetch \
            -o ./generated/ts-client \
            --additional-properties=supportsES6=true,npmName=@myorg/api-client

      - name: Upload generated client
        uses: actions/upload-artifact@v4
        with:
          name: ts-client
          path: generated/ts-client/

  publish-docs:
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build docs
        run: npx @redocly/cli build-docs openapi.yaml -o docs/index.html

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./docs
```

### Pipeline Checklist

- Lint the spec on every PR (Spectral or Redocly)
- Build docs artifact for review
- Generate SDKs after spec validation passes
- Run contract tests against generated clients
- Publish docs on merge to main
- Version the spec file with semantic versioning
