# NestJS REST Controllers — File Upload, Versioning & Error Handling

File upload with Fastify multipart, API versioning, and RFC 9457 error response standardization for NestJS 11.x.

## 5. File Upload Pattern

### Fastify Multipart Setup

```typescript
// In main.ts
import multipart from '@fastify/multipart';

async function bootstrap() {
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter()
  );

  await app.register(multipart, {
    limits: {
      fileSize: 10 * 1024 * 1024, // 10MB
      files: 5,
    },
  });

  await app.listen(3000);
}
```

### File Upload Controller

```typescript
import { Controller, Post, UseInterceptors, UploadedFile, BadRequestException } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { ApiConsumes, ApiBody, ApiOperation } from '@nestjs/swagger';

interface MulterFile {
  fieldname: string;
  originalname: string;
  encoding: string;
  mimetype: string;
  buffer: Buffer;
  size: number;
}

@Controller({ path: 'products', version: '1' })
export class ProductController {
  @Post('upload')
  @UseInterceptors(FileInterceptor('file'))
  @ApiOperation({ summary: 'Upload product image' })
  @ApiConsumes('multipart/form-data')
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        file: { type: 'string', format: 'binary' },
      },
    },
  })
  async uploadFile(@UploadedFile() file: MulterFile) {
    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
    const maxSize = 5 * 1024 * 1024; // 5MB

    if (!allowedTypes.includes(file.mimetype)) {
      throw new BadRequestException('Only JPEG, PNG, and WebP images are allowed');
    }

    // Validate actual file content by magic bytes (not just MIME type)
    // MIME type is client-spoofable — magic bytes check the real file signature
    // npm install file-type
    const { fileTypeFromBuffer } = await import('file-type');
    const detected = await fileTypeFromBuffer(file.buffer);
    if (!detected || !allowedTypes.includes(detected.mime)) {
      throw new BadRequestException(
        `File content does not match allowed types (detected: ${detected?.mime ?? 'unknown'})`,
      );
    }

    if (file.size > maxSize) {
      throw new BadRequestException('File size must not exceed 5MB');
    }

    const uploadResult = await this.productService.uploadImage(file);

    return {
      filename: file.originalname,
      size: file.size,
      mimetype: file.mimetype,
      url: uploadResult.url,
    };
  }
}
```

### Direct-to-storage uploads (presigned URL + confirm)

For files above the multipart limit the browser PUTs straight to Cloud Storage on a 15-minute V4 signed
URL; the API issues the URL and confirms the result. Same contract as FastAPI
(`python-dev/reference/fastapi-auth-security.md` §12, which also covers keyless signing on Cloud Run)
and Spring (`java-spring-api/reference/spring-boot-rest-service-guide.md`). Bucket CORS and IAM:
`gcp-cloud-run/SKILL.md`. Typings checked against `@google-cloud/storage` 9.0.0 (Node >= 22): the
method is `getSignedUrl`; `generateSignedUrl` does not exist.

```typescript
// src/upload/upload.dto.ts
import { IsIn, IsInt, IsOptional, IsString, Max, MaxLength, Min } from 'class-validator';

export const ALLOWED_TYPES = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
  'application/pdf': '.pdf',
} as const;
export type AllowedType = keyof typeof ALLOWED_TYPES;
export const MAX_BYTES = 100 * 1024 * 1024;

export class PresignedUrlRequestDto {
  // Accepted because the Angular client sends it (forbidNonWhitelisted); never used in the object key
  @IsOptional()
  @IsString()
  @MaxLength(255)
  filename?: string;

  @IsIn(Object.keys(ALLOWED_TYPES))
  contentType!: AllowedType;

  @IsInt()
  @Min(1)
  @Max(MAX_BYTES)
  size!: number;
}

export class ConfirmUploadDto {
  @IsString()
  @MaxLength(200)
  objectKey!: string;
}
```

```typescript
// src/upload/upload.service.ts   (npm install @google-cloud/storage@9.0.0)
import { randomUUID } from 'node:crypto';
import { Injectable, Logger, NotFoundException, UnprocessableEntityException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Storage, type Bucket } from '@google-cloud/storage';
import { ALLOWED_TYPES, MAX_BYTES, type PresignedUrlRequestDto } from './upload.dto';

const URL_TTL_MS = 15 * 60 * 1000;

@Injectable()
export class UploadService {
  private readonly logger = new Logger(UploadService.name);
  private readonly bucket: Bucket;

  constructor(config: ConfigService) {
    this.bucket = new Storage().bucket(config.getOrThrow<string>('GCS_UPLOAD_BUCKET'));
  }

  async createPresignedUrl(ownerId: string, dto: PresignedUrlRequestDto) {
    // Server-chosen key under the owner's directory: the client filename never reaches the key
    const objectKey = `uploads/${ownerId}/${randomUUID()}${ALLOWED_TYPES[dto.contentType]}`;
    const expiresAt = new Date(Date.now() + URL_TTL_MS);
    const [uploadUrl] = await this.bucket.file(objectKey).getSignedUrl({
      version: 'v4',
      action: 'write',
      expires: expiresAt,
      contentType: dto.contentType, // the PUT must send this exact Content-Type or GCS answers 403
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
import { CurrentPrincipal } from '../auth/auth.decorators';
import type { Principal } from '../auth/principal';
import { ConfirmUploadDto, PresignedUrlRequestDto } from './upload.dto';
import { UploadService } from './upload.service';

@Controller({ path: 'upload', version: '1' })
export class UploadController {
  constructor(private readonly uploads: UploadService) {}

  @Post('presigned-url')
  @HttpCode(200)
  presignedUrl(@CurrentPrincipal() principal: Principal, @Body() dto: PresignedUrlRequestDto) {
    return this.uploads.createPresignedUrl(principal.subject, dto);
  }

  @Post('confirm')
  @HttpCode(204)
  async confirm(@CurrentPrincipal() principal: Principal, @Body() dto: ConfirmUploadDto): Promise<void> {
    await this.uploads.confirmUpload(principal.subject, dto.objectKey);
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
