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
