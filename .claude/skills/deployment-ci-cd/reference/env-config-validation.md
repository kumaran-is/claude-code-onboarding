# Environment Configuration & Startup Validation

> Browser apps (Angular, React) cannot read server environment variables at runtime, and anything bundled is public. Use a runtime `config.json` validated at boot (fail closed): `web-frontend-delivery.md` §2.

Following Twelve-Factor App methodology (https://12factor.net/config):
- Config belongs in environment variables, NOT in code or config files committed to git
- App MUST fail fast at startup if required env vars are missing or invalid
- Different values per environment (dev/staging/prod) via env injection — same code, different config

---

## Why Fail Fast at Startup

If `DATABASE_URL` is missing and you discover it at the first DB query (30 seconds into serving traffic):
- You've already passed the health check
- Cloud Run considers the revision healthy
- Real users get errors on first request

Fail at startup → Cloud Run health check fails → new revision never gets traffic → previous revision stays live.

---

## NestJS 11.x — Zod Startup Validation

```typescript
// src/config/env.ts
import { z } from 'zod';

const envSchema = z.object({
  // Database
  DATABASE_URL: z.string().url('DATABASE_URL must be a valid URL'),

  // App
  NODE_ENV: z.enum(['development', 'staging', 'production']),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  APP_VERSION: z.string().optional(),

  // Auth
  JWT_SECRET: z.string().min(32, 'JWT_SECRET must be at least 32 characters'),

  // Optional integrations
  REDIS_URL: z.string().url().optional(),
  SMTP_HOST: z.string().optional(),
  SMTP_PORT: z.coerce.number().int().optional(),
});

// Parse at module load — throws ZodError at startup if invalid
export const env = envSchema.parse(process.env);

// Type-safe access everywhere:
// import { env } from '@/config/env';
// env.DATABASE_URL  ← fully typed, guaranteed defined
```

Register in `AppModule`:
```typescript
// src/app.module.ts
import { env } from './config/env'; // This line triggers validation at module load

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      validate: () => env, // env already validated — just return it
    }),
  ],
})
export class AppModule {}
```

---

## Spring Boot 3.5.x — `@ConfigurationProperties` Validation

```java
// src/main/java/com/example/config/AppProperties.java
@ConfigurationProperties(prefix = "app")
@Validated
public record AppProperties(
    @NotBlank String databaseUrl,
    @NotBlank @Size(min = 32) String jwtSecret,
    @Min(1) @Max(65535) int port,
    @NotNull Environment environment
) {
    public enum Environment { development, staging, production }
}
```

```yaml
# application.yml
app:
  database-url: ${DATABASE_URL}      # Required — fails startup if DATABASE_URL not set
  jwt-secret: ${JWT_SECRET}          # Required
  port: ${PORT:8080}                 # Optional with default
  environment: ${APP_ENV:production}
```

Spring Boot validates all `@ConfigurationProperties` at startup — missing required env vars throw `BindValidationException` before serving any requests.

---

## Python FastAPI 3.14 — Pydantic Settings Startup Validation

```python
# src/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl, field_validator
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Required — no default = fails startup if missing
    DATABASE_URL: AnyUrl
    JWT_SECRET: str

    # Optional with defaults
    PORT: int = 8000
    APP_ENV: Literal["development", "staging", "production"] = "production"
    APP_VERSION: str = "unknown"

    @field_validator("JWT_SECRET")
    @classmethod
    def jwt_secret_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v


# Instantiate at module load — raises ValidationError at startup if invalid
settings = Settings()
```

---

## Twelve-Factor Checklist

```
□ No config values hardcoded in source code
□ No config files committed to git (use .env.example with placeholder values)
□ All required env vars validated at startup (fail fast, not at first use)
□ .env files in .gitignore
□ .env.example committed with all keys present, values as placeholders
□ Different environments use same code, different env injection (CI/CD sets vars)
□ Secrets injected via CI/CD secrets (GitHub Actions secrets → env vars), never in compose files
□ Config is not baked into the image: no ENV for env-varying values (use ARG at build time only), compose uses bare ${VAR} with no :-default
□ The key set is identical across local / staging / production templates (parity check in CI, with a known-bad control)
□ Every var the code reads that is present in a deploy template is ALSO wired in the infrastructure code of each deployed service
  (a grep gate cannot see BaseSettings fields or computed names: verify by hand with a control grep, known-present var count = 1)
□ Required settings have NO code default, so a missing one fails startup loudly
```

---

## .env.example Template

```bash
# Required — app will not start without these
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/myapp
JWT_SECRET=<replace-with-32-char-minimum-secret>

# Required — set to: development | staging | production
NODE_ENV=development

# Optional — defaults shown
PORT=3000
APP_VERSION=local
REDIS_URL=
```
