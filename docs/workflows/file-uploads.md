# File Uploads — GCS Presigned URL Pattern

> **When to use**: Uploading files from any client (Angular, Flutter, mobile) to Google Cloud Storage without routing file bytes through your backend server
> **Time estimate**: 2–3 hours for initial setup across one stack; 30 min per additional stack
> **Prerequisites**: GCS bucket created, IAM service account with `storage.objects.create` on the bucket, Workload Identity or service account key for backend auth

## Overview

The presigned URL pattern has three steps regardless of backend stack:

```
1. Client  →  POST /api/upload/presigned-url   →  Backend
              { filename, contentType, size }

2. Backend →  validate request, generate GCS signed URL (15 min TTL)
   Backend →  return { uploadUrl, objectKey }  →  Client

3. Client  →  PUT <file bytes>                 →  GCS (direct, no backend)
              Content-Type: <exact match>

4. Client  →  POST /api/upload/confirm         →  Backend  (optional)
              { objectKey }
```

**Why presigned URLs over server-proxied upload:**

| Concern | Direct proxy | Presigned URL |
|---------|-------------|---------------|
| Backend bandwidth | Pays for every byte | Zero — client → GCS direct |
| Backend memory | File buffered in RAM | Not involved |
| Max file size | Limited by server RAM/timeout | GCS limit (5 TB) |
| Latency | Two hops (client → backend → GCS) | One hop (client → GCS) |
| Security | Backend validates before storing | Backend validates before issuing URL |

---

## Security Baseline (All Stacks)

Before issuing a presigned URL the backend MUST:

- [ ] Authenticate the request (JWT / session)
- [ ] Validate `contentType` against an allowlist — never trust the client
- [ ] Validate `size` is within limit (reject before generating URL)
- [ ] Generate a non-guessable `objectKey` (UUID prefix — never use `filename` directly)
- [ ] Set URL TTL to ≤ 15 minutes
- [ ] Scope the signed URL to the exact `contentType` passed (GCS enforces this on PUT)

```
Allowed MIME types (example allowlist):
  image/jpeg, image/png, image/webp, image/gif
  application/pdf
  video/mp4
```

---

## Backend Implementations

### NestJS (already in nestjs-rest-upload-errors.md — adding presigned URL endpoint)

```typescript
// src/upload/upload.controller.ts
import { Controller, Post, Body, UseGuards, HttpCode } from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { UploadService } from './upload.service';
import { PresignedUrlRequestDto, PresignedUrlResponseDto } from './upload.dto';

@Controller('upload')
@UseGuards(JwtAuthGuard)
export class UploadController {
  constructor(private readonly uploadService: UploadService) {}

  @Post('presigned-url')
  @HttpCode(200)
  async getPresignedUrl(
    @Body() dto: PresignedUrlRequestDto,
  ): Promise<PresignedUrlResponseDto> {
    return this.uploadService.createPresignedUrl(dto);
  }

  @Post('confirm')
  @HttpCode(204)
  async confirmUpload(@Body('objectKey') objectKey: string): Promise<void> {
    await this.uploadService.confirmUpload(objectKey);
  }
}
```

```typescript
// src/upload/upload.dto.ts
import { IsString, IsIn, IsInt, Max, Min } from 'class-validator';

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'] as const;
const MAX_BYTES = 100 * 1024 * 1024; // 100 MB

export class PresignedUrlRequestDto {
  @IsString()
  filename: string;

  @IsIn(ALLOWED_TYPES)
  contentType: string;

  @IsInt()
  @Min(1)
  @Max(MAX_BYTES)
  size: number;
}

export class PresignedUrlResponseDto {
  uploadUrl: string;
  objectKey: string;
  expiresAt: string;
}
```

```typescript
// src/upload/upload.service.ts
import { Injectable, Logger } from '@nestjs/common';
import { Storage } from '@google-cloud/storage';
import { randomUUID } from 'crypto';
import { extname } from 'path';
import { PresignedUrlRequestDto, PresignedUrlResponseDto } from './upload.dto';

@Injectable()
export class UploadService {
  private readonly logger = new Logger(UploadService.name);
  private readonly storage = new Storage();
  private readonly bucket = this.storage.bucket(process.env.GCS_BUCKET!);

  async createPresignedUrl(dto: PresignedUrlRequestDto): Promise<PresignedUrlResponseDto> {
    // Sanitize filename — never trust client-provided names for object keys
    const ext = extname(dto.filename).toLowerCase().replace(/[^a-z0-9.]/g, '');
    const objectKey = `uploads/${randomUUID()}${ext}`;

    const expiresAt = new Date(Date.now() + 15 * 60 * 1000);
    const file = this.bucket.file(objectKey);

    const [uploadUrl] = await file.generateSignedUrl({
      version: 'v4',
      action: 'write',
      expires: expiresAt,
      contentType: dto.contentType,  // GCS enforces Content-Type match on PUT
    });

    this.logger.log(`Presigned URL issued for objectKey=${objectKey}`);
    return { uploadUrl, objectKey, expiresAt: expiresAt.toISOString() };
  }

  async confirmUpload(objectKey: string): Promise<void> {
    // Verify object actually exists in GCS before marking as complete
    const [exists] = await this.bucket.file(objectKey).exists();
    if (!exists) {
      this.logger.error(`confirmUpload: objectKey=${objectKey} not found in GCS`);
      throw new Error(`Object not found: ${objectKey}`);
    }
    this.logger.log(`Upload confirmed: objectKey=${objectKey}`);
    // Persist objectKey to your database here
  }
}
```

```
# Install
npm install @google-cloud/storage
```

---

### Python FastAPI

```python
# src/upload/router.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from google.cloud import storage
from datetime import timedelta
from pathlib import Path
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_BYTES = 100 * 1024 * 1024  # 100 MB


class PresignedUrlRequest(BaseModel):
    filename: str
    content_type: str
    size: int

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        if v not in ALLOWED_TYPES:
            raise ValueError(f"content_type not allowed: {v}")
        return v

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: int) -> int:
        if v < 1 or v > MAX_BYTES:
            raise ValueError(f"size must be between 1 and {MAX_BYTES} bytes")
        return v


class PresignedUrlResponse(BaseModel):
    upload_url: str
    object_key: str
    expires_at: str


@router.post("/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(
    request: PresignedUrlRequest,
    # current_user = Depends(get_current_user),  # add your auth dependency
) -> PresignedUrlResponse:
    # Sanitize extension — never use client filename directly as object key
    suffix = Path(request.filename).suffix.lower()
    safe_suffix = "".join(c for c in suffix if c.isalnum() or c == ".")
    object_key = f"uploads/{uuid.uuid4()}{safe_suffix}"

    client = storage.Client()
    bucket = client.bucket("YOUR_GCS_BUCKET")  # inject via settings
    blob = bucket.blob(object_key)

    upload_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=15),
        method="PUT",
        content_type=request.content_type,  # GCS enforces this on PUT
    )

    from datetime import datetime, timezone
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()

    logger.info("Presigned URL issued", extra={"object_key": object_key})
    return PresignedUrlResponse(
        upload_url=upload_url,
        object_key=object_key,
        expires_at=expires_at,
    )


class ConfirmRequest(BaseModel):
    object_key: str


@router.post("/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_upload(request: ConfirmRequest) -> None:
    client = storage.Client()
    bucket = client.bucket("YOUR_GCS_BUCKET")
    blob = bucket.blob(request.object_key)

    if not blob.exists():
        logger.error("confirm_upload: object not found", extra={"object_key": request.object_key})
        raise HTTPException(status_code=404, detail="Upload not found in storage")

    logger.info("Upload confirmed", extra={"object_key": request.object_key})
    # Persist object_key to database here
```

```
# Install
uv add google-cloud-storage
```

---

### Java Spring Boot WebFlux

```java
// src/main/java/com/example/upload/UploadController.java
package com.example.upload;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/upload")
public class UploadController {

    private final UploadService uploadService;

    public UploadController(UploadService uploadService) {
        this.uploadService = uploadService;
    }

    @PostMapping("/presigned-url")
    @ResponseStatus(HttpStatus.OK)
    public Mono<PresignedUrlResponse> getPresignedUrl(@RequestBody @Valid PresignedUrlRequest request) {
        return Mono.fromCallable(() -> uploadService.createPresignedUrl(request))
                   .subscribeOn(Schedulers.boundedElastic()); // GCS SDK is blocking
    }

    @PostMapping("/confirm")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> confirmUpload(@RequestBody ConfirmRequest request) {
        return Mono.fromCallable(() -> {
            uploadService.confirmUpload(request.objectKey());
            return null;
        }).subscribeOn(Schedulers.boundedElastic()).then();
    }
}
```

```java
// src/main/java/com/example/upload/UploadService.java
package com.example.upload;

import com.google.cloud.storage.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URL;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Service
public class UploadService {

    private static final Logger log = LoggerFactory.getLogger(UploadService.class);
    private static final Set<String> ALLOWED_TYPES =
        Set.of("image/jpeg", "image/png", "image/webp", "application/pdf");
    private static final long MAX_BYTES = 100L * 1024 * 1024; // 100 MB

    @Value("${gcs.bucket}")
    private String bucketName;

    private final Storage storage = StorageOptions.getDefaultInstance().getService();

    public PresignedUrlResponse createPresignedUrl(PresignedUrlRequest request) {
        if (!ALLOWED_TYPES.contains(request.contentType())) {
            throw new IllegalArgumentException("Content type not allowed: " + request.contentType());
        }
        if (request.size() < 1 || request.size() > MAX_BYTES) {
            throw new IllegalArgumentException("File size out of range");
        }

        // Sanitize — never use client filename directly
        String ext = extractSafeExtension(request.filename());
        String objectKey = "uploads/" + UUID.randomUUID() + ext;

        BlobInfo blobInfo = BlobInfo.newBuilder(BlobId.of(bucketName, objectKey))
            .setContentType(request.contentType())
            .build();

        URL uploadUrl = storage.signUrl(
            blobInfo,
            15, TimeUnit.MINUTES,
            Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
            Storage.SignUrlOption.withV4Signature(),
            Storage.SignUrlOption.withExtHeaders(
                java.util.Map.of("Content-Type", request.contentType())
            )
        );

        String expiresAt = Instant.now().plusSeconds(900).toString();
        log.info("Presigned URL issued objectKey={}", objectKey);
        return new PresignedUrlResponse(uploadUrl.toString(), objectKey, expiresAt);
    }

    public void confirmUpload(String objectKey) {
        Blob blob = storage.get(BlobId.of(bucketName, objectKey));
        if (blob == null || !blob.exists()) {
            log.error("confirmUpload: objectKey={} not found in GCS", objectKey);
            throw new IllegalStateException("Object not found: " + objectKey);
        }
        log.info("Upload confirmed objectKey={}", objectKey);
        // Persist objectKey to database here
    }

    private String extractSafeExtension(String filename) {
        int dot = filename.lastIndexOf('.');
        if (dot < 0) return "";
        String ext = filename.substring(dot).toLowerCase();
        return ext.replaceAll("[^a-z0-9.]", ""); // strip anything non-alphanumeric
    }
}
```

```java
// src/main/java/com/example/upload/UploadDto.java
package com.example.upload;

import jakarta.validation.constraints.*;

public record PresignedUrlRequest(
    @NotBlank String filename,
    @NotBlank String contentType,
    @Min(1) @Max(104857600) long size  // max 100 MB
) {}

public record PresignedUrlResponse(
    String uploadUrl,
    String objectKey,
    String expiresAt
) {}

public record ConfirmRequest(
    @NotBlank String objectKey
) {}
```

```xml
<!-- pom.xml -->
<dependency>
  <groupId>com.google.cloud</groupId>
  <artifactId>google-cloud-storage</artifactId>
  <version>2.43.1</version>
</dependency>
```

---

## Angular Client (presigned URL flow)

See `.claude/skills/angular-spa/reference/angular-ui-form-components.md` § Section F — Pattern 2 for the full Angular component with signals, progress bar, and error states.

**Quick reference — the three HTTP calls:**

```typescript
// Step 1: request URL from your backend
this.http.post<PresignedUrlResponse>('/api/upload/presigned-url', {
  filename: file.name, contentType: file.type, size: file.size
})

// Step 2: PUT directly to GCS (no backend)
const req = new HttpRequest('PUT', uploadUrl, file, {
  headers: new HttpHeaders({ 'Content-Type': file.type }),  // MUST match what backend used when signing
  reportUploadProgress: true  // Angular 22: reportProgress is deprecated
});
this.http.request(req)  // listen for HttpEventType.UploadProgress
// The default FetchBackend throws on reportUploadProgress: register provideHttpClient(withXhr()) (browser only)

// Step 3: confirm with backend
this.http.post('/api/upload/confirm', { objectKey })
```

---

## GCS Bucket Setup

```bash
# Create bucket
gcloud storage buckets create gs://YOUR_BUCKET \
  --location=us-central1 \
  --uniform-bucket-level-access

# CORS — required for browser PUT requests to GCS
cat > cors.json << 'EOF'
[{
  "origin": ["https://your-app.com"],
  "method": ["PUT"],
  "responseHeader": ["Content-Type"],
  "maxAgeSeconds": 3600
}]
EOF
gcloud storage buckets update gs://YOUR_BUCKET --cors-file=cors.json

# IAM — grant backend service account write access
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET \
  --member="serviceAccount:YOUR_SA@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"

# Verify CORS is applied
gcloud storage buckets describe gs://YOUR_BUCKET --format="json(cors)"
```

**CORS is mandatory.** Without it the browser blocks the PUT response and the upload silently appears to succeed but the `HttpEventType.Response` event never fires.

---

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| `Content-Type` on PUT doesn't match what was used to sign | GCS returns 403 | Backend signs with exact `contentType`; Angular sets same header on PUT |
| Client filename used as GCS object key | Path traversal, filename collision | Always use `UUID + safe extension` as object key |
| No CORS config on bucket | Browser blocks response, upload appears to hang | `gcloud storage buckets update --cors-file=cors.json` |
| Presigned URL logged or returned to unauthenticated callers | URL is a 15-min credential | Never log full URL; require auth on presigned-url endpoint |
| No size validation before issuing URL | DoS — client uploads 10 GB | Validate `size` in DTO before calling GCS SDK |
| Skipping confirm step | Backend has no record of what was uploaded | Always confirm; verify blob.exists() server-side |

---

## Related

- [`deployment-ci-cd.md`](deployment-ci-cd.md) — CI/CD for backend services that serve the upload endpoints
- [`security-audit.md`](security-audit.md) — security review after implementing upload endpoints
- `.claude/skills/angular-spa/reference/angular-ui-form-components.md` § Section F — Angular UI component with both upload patterns
- `.claude/skills/nestjs-api/reference/nestjs-rest-upload-errors.md` — direct multipart POST pattern for NestJS (files ≤ 10 MB)
