# NestJS Security — Validation, Logging & Prisma

Input validation hardening, PII masking in logs, Prisma security patterns, and OWASP checklist for NestJS 12.x. For dependency scanning, headers, and CORS, see `nestjs-security-scanning.md`.

**Note:** For authentication and authorization patterns (JWT, passwords, rate limiting), see `nestjs-security-auth.md`.

## 1. Input Validation Hardening

### Request schema hardening (Zod 4, Standard Schema)

```typescript
// src/features/users/users.schemas.ts
import { z } from 'zod';

export const CreateUserSchema = z
  .strictObject({
    // Normalize before validating; uniqueness is enforced by the database (unique index), not here.
    email: z.string().trim().toLowerCase().pipe(z.email().max(255)),
    // Length is the strength control (NIST SP 800-63B): long passphrases, no composition rules,
    // 128-char cap so the hash input stays bounded. Check breached-password lists in the service.
    password: z.string().min(12).max(128),
    firstName: z
      .string()
      .trim()
      .min(2)
      .max(50)
      .regex(/^[\p{L}\p{M}' -]+$/u, 'contains invalid characters'),
    tags: z.array(z.string().trim().min(1).max(30)).max(10).default([]),
  })
  .meta({ id: 'CreateUser' });
export type CreateUser = z.infer<typeof CreateUserSchema>;
```

```typescript
@Post()
@Public()
create(@Body({ schema: CreateUserSchema }) body: CreateUser) {
  return this.users.register(body);
}
```

- `z.strictObject` rejects unknown keys with 400 (a smuggled `role` or `tenantId` never reaches the handler).
- Every string and array is bounded; Fastify's `bodyLimit` bounds the whole request (413 above it).
- Do not HTML-sanitize on input: store what was validated and encode on output (Angular/React escape by default).
  Sanitizing input corrupts legitimate data and is not a substitute for output encoding.
- The validation error lists `"path: message"` entries and never echoes the submitted value (verified: an
  `<script>` payload in `sku` is absent from the 400 body).

### Global validation

```typescript
// src/app.module.ts (excerpt): validates every parameter declared with { schema }
import { StandardSchemaValidationPipe } from '@nestjs/common';
import { APP_PIPE } from '@nestjs/core';

providers: [{ provide: APP_PIPE, useValue: new StandardSchemaValidationPipe() }];
```

**Existing class-validator codebases:** `ValidationPipe` is still supported in NestJS 12; keep
`whitelist: true, forbidNonWhitelisted: true, transform: true, transformOptions: { enableImplicitConversion: false }`,
and use `@ValidateIf((_, value) => value !== undefined)` where `null` must be rejected (`@IsOptional()` lets it through).

## 2. Secure Logging — PII Masking

### Log Sanitizer Service

```typescript
// src/common/logging/log-sanitizer.service.ts
import { Injectable } from '@nestjs/common';

@Injectable()
export class LogSanitizerService {
  private readonly sensitivePatterns = [
    { pattern: /"password":\s*"[^"]*"/gi, replacement: '"password":"***MASKED***"' },
    { pattern: /"token":\s*"[^"]*"/gi, replacement: '"token":"***MASKED***"' },
    { pattern: /\b\d{3}-\d{2}-\d{4}\b/g, replacement: '***-**-****' }, // SSN
    { pattern: /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/g, replacement: '****-****-****-****' }, // Credit card
  ];

  sanitize(data: unknown): unknown {
    if (typeof data === 'string') {
      return this.sanitizeString(data);
    }
    if (Array.isArray(data)) {
      return data.map((item) => this.sanitize(item));
    }
    if (typeof data === 'object' && data !== null) {
      return this.sanitizeObject(data);
    }
    return data;
  }

  private sanitizeString(str: string): string {
    let sanitized = str;
    for (const { pattern, replacement } of this.sensitivePatterns) {
      sanitized = sanitized.replace(pattern, replacement);
    }
    return sanitized;
  }

  private sanitizeObject(obj: Record<string, unknown>): Record<string, unknown> {
    const sanitized: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      sanitized[key] = this.isSensitiveKey(key) ? this.maskValue(value) : this.sanitize(value);
    }
    return sanitized;
  }

  private isSensitiveKey(key: string): boolean {
    const sensitiveKeys = ['password', 'token', 'apiKey', 'secret', 'ssn', 'creditCard'];
    return sensitiveKeys.some((s) => key.toLowerCase().includes(s.toLowerCase()));
  }

  private maskValue(value: unknown): string {
    if (typeof value !== 'string' || value.length <= 4) return '***';
    return `${value.substring(0, 2)}***${value.substring(value.length - 2)}`;
  }
}
```

## 3. Prisma Security

### Avoid SQL Injection

```typescript
import { Prisma } from '../../generated/prisma/client.js'; // Prisma 7: from the generated client

// ❌ DANGEROUS — string-built SQL through the Unsafe API
async findUserBad(email: string) {
  return this.prisma.client.$queryRawUnsafe(`SELECT * FROM users WHERE email = '${email}'`);
}

// ✅ SAFE — tagged template: every ${value} becomes a bind parameter
async findUserSafe(email: string) {
  return this.prisma.client.$queryRaw`SELECT id, email FROM users WHERE email = ${email}`;
}

// ✅ SAFE — composed fragments stay parameterized with Prisma.sql / Prisma.join
async findUsersByIds(ids: string[]) {
  return this.prisma.client.$queryRaw(
    Prisma.sql`SELECT id, email FROM users WHERE id IN (${Prisma.join(ids)})`,
  );
}

// ✅ BEST — Prisma Client methods
async findUserBest(email: string) {
  return this.prisma.client.user.findUnique({ where: { email } });
}
```

Identifiers (column or table names) cannot be bind parameters: map them from an allow-list, never from input.

### Field-Level Encryption

```typescript
// src/common/encryption/encryption.service.ts
import { Injectable } from '@nestjs/common';
import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from 'node:crypto';

@Injectable()
export class EncryptionService {
  private readonly algorithm = 'aes-256-gcm';
  private readonly key: Buffer;

  constructor() {
    this.key = scryptSync(process.env.ENCRYPTION_KEY, 'salt', 32);
  }

  encrypt(text: string): string {
    const iv = randomBytes(16);
    const cipher = createCipheriv(this.algorithm, this.key, iv);
    let encrypted = cipher.update(text, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    const authTag = cipher.getAuthTag();
    return `${iv.toString('hex')}:${authTag.toString('hex')}:${encrypted}`;
  }

  decrypt(encryptedText: string): string {
    const [ivHex, authTagHex, encrypted] = encryptedText.split(':');
    const iv = Buffer.from(ivHex, 'hex');
    const authTag = Buffer.from(authTagHex, 'hex');
    const decipher = createDecipheriv(this.algorithm, this.key, iv);
    decipher.setAuthTag(authTag);
    let decrypted = decipher.update(encrypted, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    return decrypted;
  }
}
```

### Soft Delete Pattern

```typescript
// prisma/schema.prisma
model User {
  id        String    @id @default(uuid())
  email     String    @unique
  deletedAt DateTime? @map("deleted_at")

  @@map("users")
}

// Repository
@Injectable()
export class UserRepository {
  constructor(private prisma: PrismaService) {}

  async softDelete(id: string): Promise<void> {
    await this.prisma.client.user.update({
      where: { id },
      data: { deletedAt: new Date() },
    });
  }

  async findActive(id: string) {
    return this.prisma.client.user.findFirst({
      where: { id, deletedAt: null },
    });
  }
}
```

## 4. Security Checklist

### OWASP Top 10 Mitigations

- [ ] **A01: Broken Access Control** — Implement RBAC with guards on protected routes
- [ ] **A02: Cryptographic Failures** — Use bcrypt (cost >=12), RS256 for JWT, encrypt sensitive DB fields
- [ ] **A03: Injection** — Never use string concatenation in queries (`$queryRawUnsafe`), validate all inputs with `z.strictObject` schemas
- [ ] **A04: Insecure Design** — Implement rate limiting, circuit breakers, fail-fast config
- [ ] **A05: Security Misconfiguration** — Run npm audit in CI/CD, configure Helmet, disable stack traces in prod
- [ ] **A06: Vulnerable Components** — Automate dependency scanning (Snyk), keep dependencies updated
- [ ] **A07: Auth Failures** — Short-lived tokens (15 min), refresh token rotation, token revocation, rate limit auth endpoints
- [ ] **A08: Data Integrity Failures** — Verify JWT claims, use integrity checks, implement audit logging
- [ ] **A09: Logging Failures** — Mask PII in logs, log all auth attempts, centralized logging, alerting
- [ ] **A10: SSRF** — Validate/sanitize URLs, whitelist allowed domains, use circuit breakers

### Additional Measures

- [ ] Enable CORS with explicit origin whitelist
- [ ] Implement CSP to prevent XSS
- [ ] Global `StandardSchemaValidationPipe`; request schemas are `z.strictObject` (or `whitelist` + `forbidNonWhitelisted` in a class-validator codebase)
- [ ] Soft delete pattern to prevent data loss
- [ ] Field-level encryption for sensitive data
- [ ] Automated security scanning in CI/CD
- [ ] Regular penetration testing

---

**Next Steps:**
1. Run security scan: `bash security-scan.sh`
2. Run the linter (`npm run lint`: oxlint with type-aware rules in the scaffold)
3. Review and apply all checklist items
4. Set up automated security audits in CI/CD
