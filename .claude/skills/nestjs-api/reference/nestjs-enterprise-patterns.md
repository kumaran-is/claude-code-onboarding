# NestJS Enterprise Patterns

Exception handling, validation, and API versioning patterns for NestJS 11.x.

## Exception Hierarchy

### Base Exception

```typescript
// src/common/exceptions/base.exception.ts
import { HttpException, HttpStatus } from '@nestjs/common';

export class BaseException extends HttpException {
  constructor(
    public readonly errorCode: string,
    message: string,
    status: HttpStatus,
    public readonly details?: Record<string, unknown>,
  ) {
    super({ errorCode, message, details }, status);
    this.name = this.constructor.name;
    Error.captureStackTrace(this, this.constructor);
  }
}
```

### Concrete Exceptions

```typescript
// src/common/exceptions/business.exception.ts
import { HttpStatus } from '@nestjs/common';
import { BaseException } from './base.exception';

export class BusinessException extends BaseException {
  constructor(
    errorCode: string,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(errorCode, message, HttpStatus.UNPROCESSABLE_ENTITY, details);
  }
}

// src/common/exceptions/validation.exception.ts
export class ValidationException extends BaseException {
  constructor(
    message: string,
    errors: string[] = [],
    details?: Record<string, unknown>,
  ) {
    super(
      'VALIDATION_ERROR',
      message,
      HttpStatus.BAD_REQUEST,
      { ...details, errors },
    );
  }
}

// src/common/exceptions/not-found.exception.ts
export class NotFoundException extends BaseException {
  constructor(resource: string, identifier: string | number) {
    super(
      'RESOURCE_NOT_FOUND',
      `${resource} with ID ${identifier} not found`,
      HttpStatus.NOT_FOUND,
      { resource, identifier },
    );
  }
}

// src/common/exceptions/database.exception.ts
export class DatabaseException extends BaseException {
  constructor(message: string, cause?: Error) {
    super(
      'DATABASE_ERROR',
      message,
      HttpStatus.SERVICE_UNAVAILABLE,
      { cause: cause?.message },
    );
  }
}

// src/common/exceptions/static-configuration.exception.ts
// Used by static config reader for fail-fast startup validation
export class StaticConfigurationException extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'StaticConfigurationException';
  }

  static missingEnvVar(key: string): StaticConfigurationException {
    return new StaticConfigurationException(
      `Missing required environment variable: ${key}`,
    );
  }

  static invalidEnvVar(
    key: string,
    value: string,
    expected: string,
  ): StaticConfigurationException {
    return new StaticConfigurationException(
      `Invalid environment variable ${key}="${value}". Expected: ${expected}`,
    );
  }
}
```

## Global Exception Filter

Creates RFC 9457 ProblemDetail responses for all errors.

```typescript
// src/common/filters/global-exception.filter.ts
import {
  ExceptionFilter,
  Catch,
  ArgumentsHost,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import { FastifyReply, FastifyRequest } from 'fastify';
import { PrismaClientKnownRequestError } from '@prisma/client/runtime/library';
import { BaseException } from '../exceptions/base.exception';
import { getCorrelationId } from '../context/request-context.service';

interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  errorCode?: string;
  correlationId?: string;
  timestamp: string;
  errors?: string[];
}

@Catch()
export class GlobalExceptionFilter implements ExceptionFilter {
  private readonly logger = new Logger(GlobalExceptionFilter.name);

  catch(exception: unknown, host: ArgumentsHost): void {
    const ctx = host.switchToHttp();
    const request = ctx.getRequest<FastifyRequest>();
    const reply = ctx.getResponse<FastifyReply>();

    const correlationId = getCorrelationId() ?? 'unknown';
    const instance = request.url;
    const timestamp = new Date().toISOString();

    let problemDetail: ProblemDetail;

    // Handle custom BaseException
    if (exception instanceof BaseException) {
      problemDetail = this.handleBaseException(
        exception,
        instance,
        correlationId,
        timestamp,
      );
    }
    // Handle Prisma errors
    else if (exception instanceof PrismaClientKnownRequestError) {
      problemDetail = this.handlePrismaError(
        exception,
        instance,
        correlationId,
        timestamp,
      );
    }
    // Handle NestJS HttpException
    else if (exception instanceof HttpException) {
      problemDetail = this.handleHttpException(
        exception,
        instance,
        correlationId,
        timestamp,
      );
    }
    // Handle unknown errors
    else {
      problemDetail = this.handleUnknownError(
        exception,
        instance,
        correlationId,
        timestamp,
      );
    }

    // Log error
    this.logError(request, problemDetail, exception);

    // Send response
    reply.status(problemDetail.status).send(problemDetail);
  }

  private handleBaseException(
    exception: BaseException,
    instance: string,
    correlationId: string,
    timestamp: string,
  ): ProblemDetail {
    const response = exception.getResponse() as {
      errorCode: string;
      message: string;
      details?: Record<string, unknown>;
    };

    return {
      type: 'about:blank',
      title: this.getHttpStatusText(exception.getStatus()),
      status: exception.getStatus(),
      detail: response.message,
      instance,
      errorCode: response.errorCode,
      correlationId,
      timestamp,
      ...(response.details?.errors && { errors: response.details.errors as string[] }),
    };
  }

  private handlePrismaError(
    exception: PrismaClientKnownRequestError,
    instance: string,
    correlationId: string,
    timestamp: string,
  ): ProblemDetail {
    let status: HttpStatus;
    let errorCode: string;
    let detail: string;

    switch (exception.code) {
      case 'P2002':
        // Unique constraint violation. Prisma 7 + driver adapter: meta.target is NOT set; the
        // constraint name is in meta.driverAdapterError.cause.constraint.index — read it with
        // violatedUniqueConstraint() (nestjs-config-prisma7.md) for logic, never echo it to clients.
        status = HttpStatus.CONFLICT;
        errorCode = 'DUPLICATE_RECORD';
        detail = 'A record with these values already exists';
        break;

      case 'P2025':
        // Record not found. Do not forward meta.cause: it describes the query, not the caller's input.
        status = HttpStatus.NOT_FOUND;
        errorCode = 'RECORD_NOT_FOUND';
        detail = 'Record not found';
        break;

      case 'P2003':
        // Foreign key constraint violation
        status = HttpStatus.BAD_REQUEST;
        errorCode = 'FOREIGN_KEY_VIOLATION';
        detail = 'Referenced record does not exist';
        break;

      default:
        status = HttpStatus.INTERNAL_SERVER_ERROR;
        errorCode = 'DATABASE_ERROR';
        detail = 'A database error occurred';
    }

    return {
      type: 'about:blank',
      title: this.getHttpStatusText(status),
      status,
      detail,
      instance,
      errorCode,
      correlationId,
      timestamp,
    };
  }

  private handleHttpException(
    exception: HttpException,
    instance: string,
    correlationId: string,
    timestamp: string,
  ): ProblemDetail {
    const status = exception.getStatus();
    const response = exception.getResponse();

    let detail: string;
    let errors: string[] | undefined;

    if (typeof response === 'string') {
      detail = response;
    } else if (typeof response === 'object' && response !== null) {
      const responseObj = response as Record<string, unknown>;
      detail = (responseObj.message as string) ?? exception.message;

      // Handle class-validator errors
      if (Array.isArray(responseObj.message)) {
        errors = responseObj.message as string[];
        detail = 'Validation failed';
      }
    } else {
      detail = exception.message;
    }

    return {
      type: 'about:blank',
      title: this.getHttpStatusText(status),
      status,
      detail,
      instance,
      errorCode: 'HTTP_ERROR',
      correlationId,
      timestamp,
      ...(errors && { errors }),
    };
  }

  private handleUnknownError(
    exception: unknown,
    instance: string,
    correlationId: string,
    timestamp: string,
  ): ProblemDetail {
    const error = exception instanceof Error ? exception : new Error(String(exception));

    return {
      type: 'about:blank',
      title: 'Internal Server Error',
      status: HttpStatus.INTERNAL_SERVER_ERROR,
      detail: 'An unexpected error occurred',
      instance,
      errorCode: 'INTERNAL_ERROR',
      correlationId,
      timestamp,
    };
  }

  private logError(
    request: FastifyRequest,
    problemDetail: ProblemDetail,
    exception: unknown,
  ): void {
    const logContext = {
      method: request.method,
      url: request.url,
      correlationId: problemDetail.correlationId,
      errorCode: problemDetail.errorCode,
      status: problemDetail.status,
    };

    if (problemDetail.status >= 500) {
      this.logger.error(
        `${request.method} ${request.url} ${problemDetail.status}`,
        exception instanceof Error ? exception.stack : String(exception),
        logContext,
      );
    } else {
      this.logger.warn(
        `${request.method} ${request.url} ${problemDetail.status} - ${problemDetail.detail}`,
        logContext,
      );
    }
  }

  private getHttpStatusText(status: number): string {
    const statusTexts: Record<number, string> = {
      400: 'Bad Request',
      401: 'Unauthorized',
      403: 'Forbidden',
      404: 'Not Found',
      409: 'Conflict',
      422: 'Unprocessable Entity',
      500: 'Internal Server Error',
      502: 'Bad Gateway',
      503: 'Service Unavailable',
    };

    return statusTexts[status] ?? 'Error';
  }
}
```

## Validation Pipe Configuration

Global validation with class-validator and class-transformer.

```typescript
// src/app.module.ts (excerpt)
import { Module, ValidationPipe } from '@nestjs/common';
import { APP_PIPE } from '@nestjs/core';

@Module({
  providers: [
    {
      provide: APP_PIPE,
      useFactory: (configService: ConfigService) => {
        const environment = configService.get<string>('application.environment');
        return new ValidationPipe({
          whitelist: true, // Strip unknown properties
          forbidNonWhitelisted: true, // Throw error on unknown properties
          transform: true, // Auto-transform payloads to DTO instances
          transformOptions: {
            // false: implicit conversion turns "false" into true for booleans (verified).
            // Convert explicitly with @Type(() => Number) on the DTO property.
            enableImplicitConversion: false,
          },
          disableErrorMessages: environment === 'production', // Hide details in prod
          forbidUnknownValues: true, // Reject unknown object values
          validationError: {
            target: false, // Don't expose target object in errors
            value: false, // Don't expose value in errors (security)
          },
        });
      },
      inject: [ConfigService],
    },
  ],
})
export class AppModule {}
```

## API Versioning

URI-based versioning for backward compatibility.

```typescript
// src/main.ts (excerpt)
import { VersioningType } from '@nestjs/common';

async function bootstrap() {
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter(),
  );

  // Enable URI versioning
  app.enableVersioning({
    type: VersioningType.URI,
    defaultVersion: '1',
    prefix: 'v',
  });

  await app.listen(3000);
}

bootstrap();
```

### Using Versioning in Controllers

```typescript
// src/features/users/controllers/users-v1.controller.ts
import { Controller, Get, Version } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

@Controller({ path: 'users', version: '1' })
@ApiTags('users')
export class UsersControllerV1 {
  @Get()
  findAll() {
    return { message: 'Users v1' };
  }
}

// src/features/users/controllers/users-v2.controller.ts
@Controller({ path: 'users', version: '2' })
@ApiTags('users')
export class UsersControllerV2 {
  @Get()
  findAll() {
    return { message: 'Users v2 with enhanced response' };
  }
}
```

URLs:
- `/v1/users` - Version 1
- `/v2/users` - Version 2

## Usage Notes

1. **Exception Handling**: All exceptions are caught by GlobalExceptionFilter and converted to RFC 9457 ProblemDetail format
2. **Prisma Errors**: Automatic handling of P2002 (unique constraint), P2025 (not found), P2003 (foreign key)
3. **Validation**: Global ValidationPipe with whitelist and transform enabled, hiding errors in production
4. **Versioning**: URI-based versioning (`/v1/`, `/v2/`) with default version fallback
