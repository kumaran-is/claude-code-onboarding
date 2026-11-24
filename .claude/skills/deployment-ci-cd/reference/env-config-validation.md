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

## Python FastAPI — Pydantic Settings Startup Validation

Executed on Python 3.14.10, pydantic-settings 2.16.3 (15 tests): unset `APP_ENV`, `http` JWKS URL,
`async+memory://` limiter, the Firebase emulator variable, an empty webhook-secret list, `[""]`,
`["whsec_"]`, an `sk_live_…` key in the webhook list, three webhook secrets, and CORS origins `*`,
`https://app.example.test/` and (in production) `http://…` each fail at construction. Typing the list
`list[SecretStr]` accepted `[""]` and the API key (three tests red); dropping `max_length=2`, the
https-origin rule or the deployed-environment check each turned tests red. stripe 17.1.0 itself
refuses an empty or whitespace secret at verification, so the boot check catches misconfiguration
(a wrong or truncated value) before the first webhook fails, rather than closing a forgery hole. Without
`hide_input_in_errors`, a `missing` error prints `input_value={'database_url': 'pg://hu...` — pydantic
shortens the dict to its first and last characters, so the first and last settings leak (whole, when
short) into boot logs; the flag removes `input_value`, and a test asserting the DSN prefix is absent
went red when the flag was removed.

```python
# src/my_service/core/config.py
import os
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import AfterValidator, AnyUrl, Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _webhook_secret(value: SecretStr) -> SecretStr:
    raw = value.get_secret_value()
    if not raw.startswith("whsec_") or len(raw) < len("whsec_") + 24:
        raise ValueError("expected a Stripe webhook signing secret (whsec_...)")
    return value


def _origin(value: str) -> str:
    # exactly what browsers send in Origin; HttpUrl would append "/" and never match
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.hostname or value != f"{parts.scheme}://{parts.netloc}":
        raise ValueError("CORS origin must be scheme://host[:port] (no path, no wildcard)")
    return value


WebhookSecret = Annotated[SecretStr, AfterValidator(_webhook_secret)]
Origin = Annotated[str, AfterValidator(_origin)]


class Settings(BaseSettings):
    # .env only for local runs: deployments inject real environment variables
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        hide_input_in_errors=True,  # otherwise a startup ValidationError prints the env values it read
    )

    app_env: Literal["local", "test", "staging", "production"]  # no default: unset fails startup
    database_url: SecretStr                                      # DSNs carry passwords
    jwks_url: HttpUrl
    jwt_issuer: str
    jwt_audience: str
    stripe_webhook_secrets: list[WebhookSecret] = Field(min_length=1, max_length=2)  # current, previous
    rate_limit_storage_uri: AnyUrl
    cors_origins: list[Origin] = []
    cookie_sessions: bool = False         # CORS allow_credentials and CSRF checks only when True
    port: int = 8000

    @model_validator(mode="after")
    def deployed_invariants(self) -> Self:
        if self.app_env in {"staging", "production"}:
            if self.jwks_url.scheme != "https":
                raise ValueError("jwks_url must use https outside local/test")
            if not str(self.rate_limit_storage_uri).startswith("async+redis"):
                raise ValueError("rate limiter needs shared storage outside local/test")
            if any(not o.startswith("https://") for o in self.cors_origins):
                raise ValueError("CORS origins must be https outside local/test")
            if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
                raise ValueError("FIREBASE_AUTH_EMULATOR_HOST disables token signature checks")
        return self


settings = Settings()  # module load: a ValidationError stops the process before it serves traffic
```

**Secrets never reach logs.** `SecretStr` prints as `**********` in `repr`, `str` and `model_dump()`
(executed: the DSN password and webhook secrets were absent from all three); call
`.get_secret_value()` only at the point of use. Never log `settings`, a DSN, a token, a
`Stripe-Signature` header or `str(exc)` from a client library (it can embed the request). Log the
exception type and a correlation id.

### Field-level encryption with Cloud KMS (envelope)

For values that must stay encrypted at rest beyond disk encryption (national ids, OAuth refresh
tokens of third parties): a fresh AES-256-GCM data key (DEK) per record, wrapped by a Cloud KMS key
(KEK). Only the wrapped DEK is stored; KMS never sees the data. google-cloud-kms 3.19, cryptography 50.

```python
import os
import google_crc32c
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.cloud import kms

def _crc(b: bytes) -> int:
    return google_crc32c.value(b)

async def seal(client: kms.KeyManagementServiceAsyncClient, key_name: str, plaintext: bytes, aad: bytes) -> Sealed:
    """aad binds the record to its context, e.g. b"tenant:t1|user:u1|field:national_id"."""
    dek, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
    resp = await client.encrypt(request={
        "name": key_name, "plaintext": dek, "plaintext_crc32c": _crc(dek),
        "additional_authenticated_data": aad, "additional_authenticated_data_crc32c": _crc(aad)})
    if not (resp.verified_plaintext_crc32c and resp.verified_additional_authenticated_data_crc32c
            and resp.ciphertext_crc32c == _crc(resp.ciphertext)):
        raise KmsIntegrityError("encrypt response corrupted in transit")   # retry; never store
    return Sealed(key_name, resp.ciphertext, nonce, ciphertext)

async def open_sealed(client, sealed: Sealed, aad: bytes) -> bytes:
    resp = await client.decrypt(request={
        "name": sealed.key_name, "ciphertext": sealed.wrapped_dek, "ciphertext_crc32c": _crc(sealed.wrapped_dek),
        "additional_authenticated_data": aad, "additional_authenticated_data_crc32c": _crc(aad)})
    if resp.plaintext_crc32c != _crc(resp.plaintext):
        raise KmsIntegrityError("decrypt response corrupted in transit")
    return AESGCM(resp.plaintext).decrypt(sealed.nonce, sealed.ciphertext, aad)  # InvalidTag on tamper/wrong aad
```

Store `key_name` with the record so a re-wrap job can move DEKs to a new key version without
touching data. Grant the runtime service account `roles/cloudkms.cryptoKeyEncrypterDecrypter` on
that key only. Executed against a **fake** KMS client (local AES-GCM wrap returning the real
`EncryptResponse`/`DecryptResponse` types; not live KMS): round trip, a fresh DEK per call, wrong
`aad` and a flipped ciphertext bit raise `InvalidTag`, a corrupted CRC raises `KmsIntegrityError`;
removing the CRC check or the `aad` binding turned the matching test red. Live KMS: NOT RUN (no
non-production project available to the test environment).

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

Keep it in parity with what the code reads, presence only (it never opens `.env`): `python3 .claude/scripts/check_env_parity.py <service root>` fails on a key read via `os.environ[...]`, `process.env.X`, a required `BaseSettings` field or a compose `${VAR}` that `.env.example` lacks, and warns on example keys nothing reads. Exit 2 (no `.env.example`) is BLOCKED, not clean.

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
