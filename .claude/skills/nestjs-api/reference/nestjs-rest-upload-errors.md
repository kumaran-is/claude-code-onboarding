# NestJS REST Controllers — File Upload, Versioning & Error Handling

File upload with Fastify multipart, API versioning, and RFC 9457 error response standardization for NestJS 12.x.

## 5. File Upload Pattern

### Fastify uploads with `@nestjs/platform-fastify/multipart` (NestJS 12.1+)

Since 12.1 the Fastify adapter has its own `FileInterceptor` family (`FileInterceptor`, `FilesInterceptor`,
`FileFieldsInterceptor`, `AnyFilesInterceptor`, `NoFilesInterceptor`, `FileStreamInterceptor`, `MultipartModule`) in
`@nestjs/platform-fastify/multipart`. It needs the optional peer `@fastify/multipart` (`10.1.9`, `npm i -E`), which the
adapter registers itself. The uploaded file has multer's shape, so `@UploadedFile()`, `ParseFilePipe` and the built-in
validators work unchanged. Do not import `FileInterceptor` from `@nestjs/platform-express` on Fastify.

Verified 2026-11-24 on NestJS 12.6.0 (4/4 tests: real PNG → 201; over `limits.fileSize` → 413; a shell script sent as
`image/png` → 400 by magic bytes; missing file → 400; removing `FileTypeValidator` made the spoof test fail).

```typescript
import { Controller, FileTypeValidator, HttpCode, MaxFileSizeValidator, ParseFilePipe, Post, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor, type UploadedMultipartFile } from '@nestjs/platform-fastify/multipart';
import { ApiBody, ApiConsumes } from '@nestjs/swagger';
import { ProductService } from './product.service.js';

const MAX_BYTES = 5 * 1024 * 1024;

@Controller({ path: 'products', version: '1' })
export class ProductUploadController {
  constructor(private readonly products: ProductService) {}

  @Post('image')
  @HttpCode(201)
  @ApiConsumes('multipart/form-data')
  @ApiBody({ schema: { type: 'object', properties: { file: { type: 'string', format: 'binary' } } } })
  // limits.fileSize is enforced while streaming (413); files: 1 rejects a second file.
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: MAX_BYTES, files: 1 } }))
  async upload(
    @UploadedFile(
      new ParseFilePipe({
        validators: [
          new MaxFileSizeValidator({ maxSize: MAX_BYTES }),
          // Checks the file's magic bytes, not only the client-controlled content-type.
          new FileTypeValidator({ fileType: /^image\/(png|jpeg|webp)$/ }),
        ],
      }),
    )
    file: UploadedMultipartFile,
  ): Promise<{ size: number; mimetype: string; url: string }> {
    const stored = await this.products.uploadImage({ buffer: file.buffer, mimetype: file.mimetype });
    // Never echo the client filename into storage keys or HTML; return what the server decided.
    return { size: file.size, mimetype: file.mimetype, url: stored.url };
  }
}
```

- Limits fall back to `MultipartModule`, then to the `@fastify/multipart` registration, then to its defaults: `fileSize` is
  capped by the Fastify `bodyLimit` (1 MiB unless set), `parts` by 1000, `fieldSize` 1 MB. Set `fileSize` and `files`
  per route; a raised `bodyLimit` on the adapter is still the global ceiling.
- Memory storage (the default) sets `file.buffer`; for large files use disk storage or `FileStreamInterceptor` and stream
  to object storage instead of buffering.

### Direct-to-storage uploads (presigned URL + confirm)

For files above the multipart limit the browser PUTs straight to Cloud Storage on a 15-minute V4 signed
URL; the API issues the URL and confirms the result. Same contract as FastAPI
(`python-dev/reference/fastapi-auth-security.md` §12, which also covers keyless signing on Cloud Run)
and Spring (`java-spring-api/reference/spring-boot-rest-service-guide.md`). Bucket CORS and IAM:
`gcp-cloud-run/SKILL.md`. Typings checked against `@google-cloud/storage` 9.0.0 (Node >= 22): the
method is `getSignedUrl`; `generateSignedUrl` does not exist.

```typescript
// src/upload/upload.schemas.ts
import { z } from 'zod';

export const ALLOWED_TYPES = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
  'application/pdf': '.pdf',
} as const;
export type AllowedType = keyof typeof ALLOWED_TYPES;
export const MAX_BYTES = 100 * 1024 * 1024;

const ALLOWED_TYPE_NAMES = Object.keys(ALLOWED_TYPES) as [AllowedType, ...AllowedType[]];

export const PresignedUrlRequestSchema = z
  .strictObject({
    // Accepted because the Angular client sends it (strictObject would reject it); never used in the object key
    filename: z.string().max(255).optional(),
    contentType: z.enum(ALLOWED_TYPE_NAMES),
    size: z.int().min(1).max(MAX_BYTES),
  })
  .meta({ id: 'PresignedUrlRequest' });
export type PresignedUrlRequest = z.infer<typeof PresignedUrlRequestSchema>;

export const ConfirmUploadSchema = z
  .strictObject({ objectKey: z.string().max(200) })
  .meta({ id: 'ConfirmUpload' });
export type ConfirmUpload = z.infer<typeof ConfirmUploadSchema>;
```

```typescript
// src/upload/upload.service.ts   (npm install @google-cloud/storage@9.0.0)
import { randomUUID } from 'node:crypto';
import { Injectable, Logger, NotFoundException, UnprocessableEntityException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Storage, type Bucket } from '@google-cloud/storage';
import { ALLOWED_TYPES, MAX_BYTES, type PresignedUrlRequest } from './upload.schemas.js';

const URL_TTL_MS = 15 * 60 * 1000;

@Injectable()
export class UploadService {
  private readonly logger = new Logger(UploadService.name);
  private readonly bucket: Bucket;

  constructor(config: ConfigService) {
    this.bucket = new Storage().bucket(config.getOrThrow<string>('GCS_UPLOAD_BUCKET'));
  }

  async createPresignedUrl(ownerId: string, input: PresignedUrlRequest) {
    // Server-chosen key under the owner's directory: the client filename never reaches the key
    const objectKey = `uploads/${ownerId}/${randomUUID()}${ALLOWED_TYPES[input.contentType]}`;
    const expiresAt = new Date(Date.now() + URL_TTL_MS);
    const [uploadUrl] = await this.bucket.file(objectKey).getSignedUrl({
      version: 'v4',
      action: 'write',
      expires: expiresAt,
      contentType: input.contentType, // the PUT must send this exact Content-Type or GCS answers 403
    });
    this.logger.log({ msg: 'upload_url_issued', objectKey }); // never log the URL: it is a credential
    return { uploadUrl, objectKey, expiresAt: expiresAt.toISOString() };
  }

  async confirmUpload(ownerId: string, objectKey: string): Promise<void> {
    // Exact owner-directory match; a foreign key gets the same 404 as a missing one
    if (objectKey.slice(0, objectKey.lastIndexOf('/')) !== `uploads/${ownerId}`) {
      throw new NotFoundException('Upload not found');
    }
    const file = this.bucket.file(objectKey);
    const [exists] = await file.exists();
    if (!exists) throw new NotFoundException('Upload not found');

    const [metadata] = await file.getMetadata();
    const size = Number(metadata.size);
    // The signature fixes the content type, not the size: enforce both after the fact
    const typeAllowed = Object.hasOwn(ALLOWED_TYPES, String(metadata.contentType));
    if (!Number.isFinite(size) || size > MAX_BYTES || !typeAllowed) {
      await file.delete();
      this.logger.warn({ msg: 'upload_rejected', objectKey, size });
      throw new UnprocessableEntityException('Upload rejected');
    }
    this.logger.log({ msg: 'upload_confirmed', objectKey, size });
    // Persist objectKey + owner here; malware scan / content sniffing runs asynchronously
  }
}
```

```typescript
// src/upload/upload.controller.ts  (global JwtAuthGuard: nestjs-production-baseline.md)
import { Body, Controller, HttpCode, Post } from '@nestjs/common';
import { CurrentPrincipal } from '../auth/auth.decorators.js';
import type { Principal } from '../auth/principal.js';
import {
  type ConfirmUpload,
  ConfirmUploadSchema,
  type PresignedUrlRequest,
  PresignedUrlRequestSchema,
} from './upload.schemas.js';
import { UploadService } from './upload.service.js';

@Controller({ path: 'upload', version: '1' })
export class UploadController {
  constructor(private readonly uploads: UploadService) {}

  @Post('presigned-url')
  @HttpCode(200)
  presignedUrl(
    @CurrentPrincipal() principal: Principal,
    @Body({ schema: PresignedUrlRequestSchema }) body: PresignedUrlRequest,
  ) {
    return this.uploads.createPresignedUrl(principal.subject, body);
  }

  @Post('confirm')
  @HttpCode(204)
  async confirm(
    @CurrentPrincipal() principal: Principal,
    @Body({ schema: ConfirmUploadSchema }) body: ConfirmUpload,
  ): Promise<void> {
    await this.uploads.confirmUpload(principal.subject, body.objectKey);
  }
}
```

Storage failures other than not-found propagate unchanged to the global exception filter (§7), which
logs them and answers 5xx. In a multi-tenant service put the tenant in the key too
(`uploads/${tenantId}/${subject}/...`) and in the ownership check.

---

## 6. API Versioning

### Controller Versioning

```typescript
import { Controller, VERSION_NEUTRAL } from '@nestjs/common';

// Version 1
@Controller({ path: 'products', version: '1' })
export class ProductV1Controller {
  // /v1/products
}

// Version 2 with breaking changes
@Controller({ path: 'products', version: '2' })
export class ProductV2Controller {
  // /v2/products
}

// Neutral version (no prefix)
@Controller({ path: 'health', version: VERSION_NEUTRAL })
export class HealthController {
  // /health
}
```

---

## 7. Error Response Standardization

### RFC 9457 ProblemDetail Format

```typescript
import type { FastifyReply, FastifyRequest } from 'fastify';

export class ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  timestamp: string;
  errors?: Record<string, string[]>;
}

@Catch()
export class GlobalExceptionFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<FastifyReply>();
    const request = ctx.getRequest<FastifyRequest>();

    let problem: ProblemDetail;

    if (exception instanceof HttpException) {
      problem = this.handleHttpException(exception, request);
    } else if (exception instanceof Prisma.PrismaClientKnownRequestError) {
      problem = this.handlePrismaError(exception, request);
    } else {
      problem = this.handleUnknownError(exception, request);
    }

    response.status(problem.status).send(problem);
  }

  private handlePrismaError(error: Prisma.PrismaClientKnownRequestError, request: FastifyRequest): ProblemDetail {
    switch (error.code) {
      case 'P2002': // Unique constraint violation
        // Prisma 7 + adapter: meta.target is not set (see violatedUniqueConstraint in nestjs-config-prisma7.md).
        return {
          type: 'about:blank',
          title: 'Conflict',
          status: 409,
          detail: 'A record with these values already exists',
          instance: request.url,
          timestamp: new Date().toISOString(),
        };
      case 'P2025': // Record not found
        return {
          type: 'about:blank',
          title: 'Not Found',
          status: 404,
          detail: 'The requested resource was not found',
          instance: request.url,
          timestamp: new Date().toISOString(),
        };
      default:
        return {
          type: 'about:blank',
          title: 'Internal Server Error',
          status: 500,
          detail: 'A database error occurred',
          instance: request.url,
          timestamp: new Date().toISOString(),
        };
    }
  }
}
```
