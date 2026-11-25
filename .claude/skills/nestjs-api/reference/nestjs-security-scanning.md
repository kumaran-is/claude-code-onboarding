# NestJS Security — Scanning, Headers & CORS

Dependency scanning, linting (oxlint type-aware, or ESLint security plugins), static analysis, security headers, and CORS configuration for NestJS 12.x. For input validation, PII masking, and Prisma security, see `nestjs-security-validation-logging.md`.

**Note:** For authentication and authorization patterns (JWT, passwords, rate limiting), see `nestjs-security-auth.md`.

## 1. OWASP Dependency Scanning

### NPM Audit

```bash
# Run npm audit for known CVEs
npm audit --audit-level=high

# Fix automatically where possible
npm audit fix

# Production dependencies only (npm 11: `--production` is deprecated and prints "Use `--omit=dev` instead")
npm audit --audit-level=high --omit=dev
```

### Snyk Integration

```bash
# Install Snyk CLI
npm install -g snyk

# Authenticate
snyk auth

# Test for vulnerabilities
npx snyk test

# Monitor project (sends results to Snyk dashboard)
npx snyk monitor

# Test for specific severity levels
npx snyk test --severity-threshold=high
```

### CI/CD Pipeline Integration

```yaml
# .github/workflows/security-audit.yml
name: Security Audit
on: [push, pull_request]

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version: '26.13.1'

      - name: Install dependencies
        run: npm ci

      - name: Run npm audit
        run: npm audit --audit-level=high --omit=dev

      - name: Run Snyk test
        run: npx snyk test --severity-threshold=high
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
```

## 2. Linting — oxlint (NestJS 12 default) or ESLint Security Plugins

NestJS 12's `nest new` generates **oxlint**. Type-aware rules (`no-floating-promises`, `no-misused-promises`) need
`oxlint --type-aware` with `oxlint-tsgolint`. Verified 2026-11-24 on NestJS 12.6.0 with oxlint 1.95.0 +
oxlint-tsgolint 7.0.2008: `oxlint --type-aware --deny-warnings src/ test/` exit 0 on the reference app.

```json
// .oxlintrc.json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "ignorePatterns": ["src/generated/**", "dist/**"],
  "rules": {
    "typescript/no-explicit-any": "error",
    "typescript/no-floating-promises": "error",
    "typescript/no-misused-promises": "error",
    "no-console": "error"
  },
  "env": {
    "node": true
  }
}
```

`package.json`: `"lint": "oxlint --type-aware --deny-warnings src/ test/"` (`--deny-warnings` makes warnings fail CI).

Projects that already lint with ESLint (10.15.0 + `typescript-eslint` 8.74.0, flat config) can keep it and add the
security plugin below; the example was not re-run on NestJS 12.

### Installation (ESLint)

```bash
npm install --save-dev -E eslint-plugin-security@4.2.1 @typescript-eslint/eslint-plugin@8.74.0 @typescript-eslint/parser@8.74.0
```

### eslint.config.js Configuration

```javascript
import eslintPluginSecurity from 'eslint-plugin-security';
import typescriptEslint from '@typescript-eslint/eslint-plugin';
import typescriptParser from '@typescript-eslint/parser';

export default [
  {
    files: ['src/**/*.ts'],
    languageOptions: {
      parser: typescriptParser,
      parserOptions: {
        project: './tsconfig.json',
      },
    },
    plugins: {
      '@typescript-eslint': typescriptEslint,
      security: eslintPluginSecurity,
    },
    rules: {
      // Security rules
      'security/detect-object-injection': 'error',
      'security/detect-non-literal-fs-filename': 'error',
      'security/detect-eval-with-expression': 'error',
      'security/detect-non-literal-regexp': 'warn',
      'security/detect-unsafe-regex': 'error',
      'security/detect-buffer-noassert': 'error',
      'security/detect-child-process': 'warn',
      'security/detect-disable-mustache-escape': 'error',
      'security/detect-no-csrf-before-method-override': 'error',
      'security/detect-possible-timing-attacks': 'warn',

      // TypeScript security
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unsafe-assignment': 'error',
      '@typescript-eslint/no-unsafe-call': 'error',
      '@typescript-eslint/no-unsafe-member-access': 'error',
      '@typescript-eslint/no-unsafe-return': 'error',

      // Dangerous JavaScript patterns
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'no-script-url': 'error',
      'no-with': 'error',
    },
  },
];
```

## 3. Static Analysis — Grep Patterns for Security Review

### Secrets & Credentials Detection

```bash
# Hardcoded passwords
grep -rn 'password\s*=\s*["\x27]' src/
grep -rn 'PASSWORD\s*=\s*["\x27]' src/

# API keys and tokens
grep -rn 'apiKey\s*=\s*["\x27]' src/
grep -rn 'API_KEY\s*=\s*["\x27]' src/
grep -rn 'token\s*=\s*["\x27]' src/
grep -rn 'secret\s*=\s*["\x27]' src/

# AWS credentials
grep -rn 'aws_access_key_id' src/
grep -rn 'aws_secret_access_key' src/

# Database credentials
grep -rn 'DATABASE_URL\s*=\s*["\x27]postgres' src/
```

### SQL Injection Patterns

```bash
# Dangerous Prisma raw queries with string concatenation
grep -rn '\$queryRaw.*\${' src/
grep -rn '\$executeRaw.*\${' src/
grep -rn 'queryRaw(`' src/

# String concatenation in queries
grep -rn 'prisma\.\$queryRaw.*\+' src/
```

### Missing Input Validation

```bash
# Parameters without { schema }: the global StandardSchemaValidationPipe validates ONLY parameters that declare a
# schema, so `@Body() dto: CreateOrderDto` (a type name alone) is unvalidated. One decorator per line (Prettier default).
grep -rnE --include='*.ts' '@(Body|Query|Param)\(' src/ | grep -v '{ schema'
```

### Comprehensive Security Scan Script

```bash
#!/bin/bash
# security-scan.sh

echo "=== Security Scan Report ==="
echo ""

echo "1. Searching for hardcoded secrets..."
grep -rn 'password\s*=\s*["\x27]' src/ || echo "✓ No hardcoded passwords found"
grep -rn 'apiKey\s*=\s*["\x27]' src/ || echo "✓ No hardcoded API keys found"

echo ""
echo "2. Checking for SQL injection risks..."
grep -rn '\$queryRaw.*\${' src/ || echo "✓ No unsafe raw queries found"

echo ""
echo "3. Checking for missing validation..."
unvalidated=$(grep -rnE --include='*.ts' '@(Body|Query|Param)\(' src/ | grep -v '{ schema')
if [ -n "$unvalidated" ]; then echo "$unvalidated"; echo "✗ parameters above declare no { schema }: not validated"; else echo "✓ every @Body/@Query/@Param declares { schema }"; fi

echo ""
echo "4. Checking for console.log statements..."
grep -rn 'console\.' src/ || echo "✓ No console statements in production code"

echo ""
echo "=== Scan Complete ==="
```

## 4. Security Headers — Comprehensive Helmet Configuration

### Installation

```bash
npm install @fastify/helmet
```

### main.ts Configuration

```typescript
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, NestFastifyApplication } from '@nestjs/platform-fastify';
import helmet from '@fastify/helmet';
import { AppModule } from './app.module.js';

async function bootstrap() {
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter(),
  );

  // Comprehensive Helmet configuration
  await app.register(helmet, {
    // Content Security Policy — prevents XSS attacks
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: ["'self'", "'unsafe-inline'"],
        styleSrc: ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'],
        fontSrc: ["'self'", 'https://fonts.gstatic.com'],
        imgSrc: ["'self'", 'data:', 'https:'],
        connectSrc: ["'self'", process.env.API_URL],
        objectSrc: ["'none'"],
        upgradeInsecureRequests: [],
      },
    },

    // Strict Transport Security — enforces HTTPS
    hsts: {
      maxAge: 31536000, // 1 year
      includeSubDomains: true,
      preload: true,
    },

    // X-Frame-Options — prevents clickjacking
    frameguard: {
      action: 'deny',
    },

    // X-Content-Type-Options — prevents MIME sniffing
    noSniff: true,

    // X-DNS-Prefetch-Control
    dnsPrefetchControl: {
      allow: false,
    },

    // Cross-Origin-Resource-Policy
    crossOriginResourcePolicy: {
      policy: 'same-origin',
    },

    // Cross-Origin-Opener-Policy
    crossOriginOpenerPolicy: {
      policy: 'same-origin',
    },

    // Referrer-Policy
    referrerPolicy: {
      policy: 'no-referrer',
    },

    // Permissions-Policy
    permissionsPolicy: {
      camera: ['none'],
      microphone: ['none'],
      geolocation: ['self'],
      payment: ['none'],
      usb: ['none'],
    },
  });

  await app.listen(3000, '0.0.0.0');
}
bootstrap();
```

## 5. CORS Best Practices

### Production CORS Configuration

```typescript
// src/main.ts
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter } from '@nestjs/platform-fastify';
import { ConfigService } from '@nestjs/config';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, new FastifyAdapter());
  const configService = app.get(ConfigService);

  const allowedOrigins = configService
    .get<string>('ALLOWED_ORIGINS')
    .split(',')
    .map((origin) => origin.trim());

  app.enableCors({
    origin: (origin, callback) => {
      if (!origin || allowedOrigins.includes(origin)) {
        callback(null, true);
      } else {
        callback(new Error('Not allowed by CORS'));
      }
    },
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allowedHeaders: [
      'Content-Type',
      'Authorization',
      'X-Requested-With',
      'X-Correlation-Id',
    ],
    exposedHeaders: ['X-Total-Count', 'X-Page-Number'],
    maxAge: 86400,
    preflightContinue: false,
    optionsSuccessStatus: 204,
  });

  await app.listen(3000);
}
bootstrap();
```
