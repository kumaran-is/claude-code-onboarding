# CI/CD Documentation Pipeline

Automate doc generation on every push to `main`. Adapts to the project's detected stack.

---

## GitHub Actions — Universal Doc Pipeline

```yaml
name: Generate Documentation

on:
  push:
    branches: [main, develop]
    paths:
      - 'src/**'
      - 'lib/**'
      - 'app/**'
      - 'api/**'

jobs:
  generate-docs:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      # ---- API Documentation ----
      - name: Detect stack and generate API docs
        run: |
          if [ -f pom.xml ]; then
            echo "Java/Spring — generate OpenAPI via springdoc"
            ./mvnw spring-boot:run &
            sleep 15
            curl -s http://localhost:8080/v3/api-docs > docs/api/openapi.json
          elif [ -f package.json ]; then
            echo "NestJS — generate OpenAPI via @nestjs/swagger"
            npm ci
            npm run docs:generate 2>/dev/null || echo "No docs:generate script — add one"
          elif [ -f pyproject.toml ]; then
            echo "Python FastAPI — OpenAPI is auto-served at /openapi.json"
            pip install -r requirements.txt
            uvicorn app.main:app &
            sleep 5
            curl -s http://localhost:8000/openapi.json > docs/api/openapi.json
          fi

      # ---- OpenAPI → HTML ----
      - name: Install Redocly CLI
        run: npm install -g @redocly/cli

      - name: Build HTML API docs
        run: |
          if [ -f docs/api/openapi.json ] || [ -f docs/api/openapi.yaml ]; then
            SPEC=$(ls docs/api/openapi.{json,yaml} 2>/dev/null | head -1)
            redocly build-docs $SPEC -o docs/api/index.html
            echo "API docs rendered to docs/api/index.html"
          else
            echo "[SKIP] No OpenAPI spec found at docs/api/"
          fi

      # ---- Architecture Diagram validation ----
      - name: Validate Mermaid diagrams
        run: |
          if command -v npx &>/dev/null; then
            find docs/diagrams -name "*.md" -exec \
              npx @mermaid-js/mermaid-cli -i {} -o /tmp/mermaid-out.png \; \
              2>&1 | grep -i error || echo "All diagrams valid"
          fi

      # ---- Commit generated docs ----
      - name: Commit updated docs
        uses: stefanzweifel/git-auto-commit-action@d0b01107b5db882071f96de5dd4b54961ea93f4c # v7.2.1
        with:
          commit_message: "docs: auto-generate API docs and diagrams [skip ci]"
          file_pattern: "docs/**"
          commit_user_name: "github-actions[bot]"
          commit_user_email: "github-actions[bot]@users.noreply.github.com"

      # ---- Deploy to GitHub Pages ----
      - name: Deploy to GitHub Pages
        if: github.ref == 'refs/heads/main'
        uses: peaceiris/actions-gh-pages@84c30a85c19949d7eee79c4ff27748b70285e453 # v4.1.0
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./docs
          destination_dir: .
```

---

## NestJS — OpenAPI generation script

Add to `package.json` scripts:

```json
{
  "scripts": {
    "docs:generate": "ts-node scripts/generate-openapi.ts"
  }
}
```

`scripts/generate-openapi.ts`:

```typescript
import { NestFactory } from '@nestjs/core';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { AppModule } from '../src/app.module';
import * as fs from 'fs';

async function generateOpenApi() {
  const app = await NestFactory.create(AppModule, { logger: false });
  const config = new DocumentBuilder()
    .setTitle('API')
    .setVersion('1.0')
    .addBearerAuth()
    .build();
  const document = SwaggerModule.createDocument(app, config);
  fs.writeFileSync('docs/api/openapi.json', JSON.stringify(document, null, 2));
  await app.close();
}

generateOpenApi();
```

---

## Java / Spring Boot — springdoc-openapi

Add to `pom.xml`:

```xml
<dependency>
  <groupId>org.springdoc</groupId>
  <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
  <version>2.6.0</version>
</dependency>
```

OpenAPI spec auto-served at: `http://localhost:8080/v3/api-docs`
Swagger UI at: `http://localhost:8080/swagger-ui.html`

---

## Documentation Coverage Gate

Add as a CI step to block PRs with insufficient docstring coverage:

```bash
#!/bin/bash
# scripts/check-doc-coverage.sh

THRESHOLD=${1:-80}  # default 80%

if [ -f pyproject.toml ]; then
  # Python: count def without docstring on next line
  TOTAL=$(grep -r "def " src/ --include="*.py" | wc -l)
  DOCUMENTED=$(grep -A1 "def " src/ --include="*.py" -r | grep '"""' | wc -l)
elif [ -f package.json ]; then
  # TypeScript: count exported functions without preceding JSDoc
  TOTAL=$(grep -r "^export " src/ --include="*.ts" | wc -l)
  DOCUMENTED=$(grep -B1 "^export " src/ --include="*.ts" -r | grep "\*/" | wc -l)
else
  echo "Coverage check not configured for this stack"
  exit 0
fi

COVERAGE=$(( DOCUMENTED * 100 / TOTAL ))
echo "Documentation coverage: ${COVERAGE}% (${DOCUMENTED}/${TOTAL})"

if [ "$COVERAGE" -lt "$THRESHOLD" ]; then
  echo "FAIL: Below ${THRESHOLD}% threshold"
  exit 1
fi
echo "PASS"
```

---

## Pre-commit hook (local dev)

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: check-doc-coverage
        name: Documentation coverage
        entry: bash scripts/check-doc-coverage.sh 70
        language: system
        pass_filenames: false
        stages: [commit]
```
