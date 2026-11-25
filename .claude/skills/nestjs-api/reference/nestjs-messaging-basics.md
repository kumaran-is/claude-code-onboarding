# NestJS Messaging — Background Jobs with BullMQ

Core messaging patterns for background job processing using BullMQ with Redis.

## Platform Selection Guide

| Aspect | BullMQ (Redis) | RabbitMQ (AMQP) | Kafka (Streaming) |
|--------|----------------|-----------------|-------------------|
| **Best For** | Background jobs, delayed tasks | Reliable messaging, RPC, complex routing | High-throughput streaming, analytics |
| **NestJS Integration** | Excellent (`@nestjs/bullmq`) | Good (`@golevelup/nestjs-rabbitmq`) | Solid (`kafkajs`) |
| **Throughput** | ~10k-100k jobs/sec | High (needs tuning) | Millions/sec |
| **Complexity** | Low | Medium | High |
| **Use When** | You already have Redis, need job scheduling | Cross-language services, guaranteed delivery | Event sourcing, 1M+ events/day |

## BullMQ — Background Job Processing

Verified pins (2026-11-24): `@nestjs/bullmq` 12.0.2, `bullmq` 6.7.10, **`ioredis` 6.1.0 as a direct dependency**.
BullMQ 6 made `ioredis` optional: without it the app compiles and then fails when the queue starts
(`BullMQ could not load the optional 'ioredis' package`). Dashboard: `@bull-board/nestjs` + `@bull-board/fastify`
9.14.0 (peer `@nestjs/core` `^12.0.0`).

### Queue Module

```typescript
/**
 * BullMQ Queue Module
 *
 * Enterprise-grade background job processing with:
 * - Redis-backed persistent queues
 * - Job retries with exponential backoff
 * - Job prioritization and scheduling
 * - Bull Board dashboard for monitoring
 * - Dead letter queue for failed jobs
 */

import { Module, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { BullModule } from '@nestjs/bullmq';
import { BullBoardModule } from '@bull-board/nestjs';
import { BullMQAdapter } from '@bull-board/api/bullMQAdapter';
import { FastifyAdapter } from '@bull-board/fastify'; // this stack runs on Fastify, not Express

import { QueueConfigurationService } from './configs/queue-configuration.service.js';
import { QueueOrchestratorService } from './services/queue-orchestrator.service.js';

// Queue names as constants
export const QUEUE_NAMES = {
  EMAIL: 'email',
  NOTIFICATIONS: 'notifications',
  REPORTS: 'reports',
  DATA_SYNC: 'data-sync',
  WEBHOOKS: 'webhooks',
} as const;

@Module({
  imports: [
    // Register BullMQ with Redis connection
    BullModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (configService: ConfigService) => ({
        connection: {
          host: configService.getOrThrow<string>('cache.redis.host'),
          port: configService.getOrThrow<number>('cache.redis.port'),
          password: configService.get<string>('cache.redis.password'),
          // From REDIS_QUEUE_DB: z.coerce.number().int().min(0).default(1) in src/config/env.ts, mapped by the cache config.
          db: configService.getOrThrow<number>('cache.redis.queueDb'),
        },
        defaultJobOptions: {
          attempts: 3,
          backoff: {
            type: 'exponential',
            delay: 1000,
          },
          removeOnComplete: {
            age: 3600, // Keep completed jobs for 1 hour
            count: 1000, // Keep last 1000 completed jobs
          },
          removeOnFail: {
            age: 86400 * 7, // Keep failed jobs for 7 days
          },
        },
      }),
    }),

    // Register individual queues
    BullModule.registerQueue(
      { name: QUEUE_NAMES.EMAIL },
      { name: QUEUE_NAMES.NOTIFICATIONS },
      { name: QUEUE_NAMES.REPORTS },
      { name: QUEUE_NAMES.DATA_SYNC },
      { name: QUEUE_NAMES.WEBHOOKS },
    ),

    // Bull Board dashboard (optional, disable in production if needed)
    BullBoardModule.forRoot({
      route: '/admin/queues',
      adapter: FastifyAdapter,
    }),
    BullBoardModule.forFeature(
      { name: QUEUE_NAMES.EMAIL, adapter: BullMQAdapter },
      { name: QUEUE_NAMES.NOTIFICATIONS, adapter: BullMQAdapter },
      { name: QUEUE_NAMES.REPORTS, adapter: BullMQAdapter },
      { name: QUEUE_NAMES.DATA_SYNC, adapter: BullMQAdapter },
      { name: QUEUE_NAMES.WEBHOOKS, adapter: BullMQAdapter },
    ),
  ],
  providers: [
    QueueConfigurationService,
    QueueOrchestratorService,
  ],
  exports: [
    BullModule,
    QueueOrchestratorService,
  ],
})
export class QueuesModule implements OnModuleInit {
  private readonly logger = new Logger(QueuesModule.name);

  onModuleInit(): void {
    this.logger.log('BullMQ Queues Module initialized');
    this.logger.log(`Registered queues: ${Object.values(QUEUE_NAMES).join(', ')}`);
    this.logger.log('Bull Board dashboard available at /admin/queues');
  }
}
```

### Queue Orchestrator Service

```typescript
/**
 * Queue Orchestrator Service
 *
 * Single entry point for all queue operations.
 * Provides a unified API for adding jobs across all queues.
 */

import { Injectable, Logger } from '@nestjs/common';
import { InjectQueue } from '@nestjs/bullmq';
import { Queue, Job, JobsOptions } from 'bullmq';

import { QUEUE_NAMES } from '../queues.module.js';
import { getCorrelationId } from '../../../common/context/request-context.service.js';

export interface JobData {
  [key: string]: unknown;
}

export interface QueueJobOptions extends JobsOptions {
  correlationId?: string;
}

@Injectable()
export class QueueOrchestratorService {
  private readonly logger = new Logger(QueueOrchestratorService.name);

  constructor(
    @InjectQueue(QUEUE_NAMES.EMAIL) private readonly emailQueue: Queue,
    @InjectQueue(QUEUE_NAMES.NOTIFICATIONS) private readonly notificationsQueue: Queue,
    @InjectQueue(QUEUE_NAMES.REPORTS) private readonly reportsQueue: Queue,
    @InjectQueue(QUEUE_NAMES.DATA_SYNC) private readonly dataSyncQueue: Queue,
    @InjectQueue(QUEUE_NAMES.WEBHOOKS) private readonly webhooksQueue: Queue,
  ) {}

  /**
   * Add an email job to the queue
   */
  async addEmailJob(
    jobName: string,
    data: JobData,
    options?: QueueJobOptions
  ): Promise<Job> {
    return this.addJob(this.emailQueue, jobName, data, options);
  }

  /**
   * Add a notification job to the queue
   */
  async addNotificationJob(
    jobName: string,
    data: JobData,
    options?: QueueJobOptions
  ): Promise<Job> {
    return this.addJob(this.notificationsQueue, jobName, data, options);
  }

  /**
   * Add a report generation job to the queue
   */
  async addReportJob(
    jobName: string,
    data: JobData,
    options?: QueueJobOptions
  ): Promise<Job> {
    // Reports typically need more time
    return this.addJob(this.reportsQueue, jobName, data, {
      ...options,
      attempts: 2,
      backoff: { type: 'fixed', delay: 5000 },
    });
  }

  /**
   * Add a data sync job to the queue
   */
  async addDataSyncJob(
    jobName: string,
    data: JobData,
    options?: QueueJobOptions
  ): Promise<Job> {
    return this.addJob(this.dataSyncQueue, jobName, data, options);
  }

  /**
   * Add a webhook delivery job to the queue
   */
  async addWebhookJob(
    jobName: string,
    data: JobData,
    options?: QueueJobOptions
  ): Promise<Job> {
    // Webhooks need quick retries
    return this.addJob(this.webhooksQueue, jobName, data, {
      ...options,
      attempts: 5,
      backoff: { type: 'exponential', delay: 500 },
    });
  }

  /**
   * Schedule a recurring job
   */
  async addRecurringJob(
    queueName: keyof typeof QUEUE_NAMES,
    jobName: string,
    data: JobData,
    cron: string
  ): Promise<Job> {
    const queue = this.getQueue(queueName);
    return this.addJob(queue, jobName, data, {
      repeat: { pattern: cron },
    });
  }

  /**
   * Schedule a delayed job
   */
  async addDelayedJob(
    queueName: keyof typeof QUEUE_NAMES,
    jobName: string,
    data: JobData,
    delayMs: number
  ): Promise<Job> {
    const queue = this.getQueue(queueName);
    return this.addJob(queue, jobName, data, { delay: delayMs });
  }

  /**
   * Get queue metrics
   */
  async getQueueMetrics(): Promise<Record<string, unknown>> {
    const queues = [
      this.emailQueue,
      this.notificationsQueue,
      this.reportsQueue,
      this.dataSyncQueue,
      this.webhooksQueue,
    ];

    const metrics: Record<string, unknown> = {};

    for (const queue of queues) {
      const [waiting, active, completed, failed, delayed] = await Promise.all([
        queue.getWaitingCount(),
        queue.getActiveCount(),
        queue.getCompletedCount(),
        queue.getFailedCount(),
        queue.getDelayedCount(),
      ]);

      metrics[queue.name] = {
        waiting,
        active,
        completed,
        failed,
        delayed,
        total: waiting + active + delayed,
      };
    }

    return metrics;
  }

  private getQueue(queueName: keyof typeof QUEUE_NAMES): Queue {
    const queueMap: Record<string, Queue> = {
      EMAIL: this.emailQueue,
      NOTIFICATIONS: this.notificationsQueue,
      REPORTS: this.reportsQueue,
      DATA_SYNC: this.dataSyncQueue,
      WEBHOOKS: this.webhooksQueue,
    };
    return queueMap[queueName];
  }

  private async addJob(
    queue: Queue,
    jobName: string,
    data: JobData,
    options?: QueueJobOptions
  ): Promise<Job> {
    // Inject correlation ID for tracing
    const correlationId = options?.correlationId ?? getCorrelationId() ?? 'unknown';

    const enrichedData = {
      ...data,
      _meta: {
        correlationId,
        enqueuedAt: new Date().toISOString(),
      },
    };

    const job = await queue.add(jobName, enrichedData, options);

    this.logger.debug(
      `Job added: ${queue.name}/${jobName} (${job.id}) - correlationId: ${correlationId}`
    );

    return job;
  }
}
```

### Base Job Processor

```typescript
/**
 * Base Job Processor
 *
 * Abstract base class for all job processors with:
 * - Automatic logging with correlation ID
 * - Error handling and reporting
 * - Metrics collection
 * - Request context propagation
 */

import { Logger } from '@nestjs/common';
import { Job } from 'bullmq';
import { runWithContext, RequestContext } from '../../../common/context/request-context.service.js';

export interface JobMeta {
  correlationId: string;
  enqueuedAt: string;
}

export abstract class BaseProcessor {
  protected abstract readonly logger: Logger;
  /** e.g. an OTel Counter (or @prometheus-io/client, successor of the deprecated prom-client) with labels ['queue', 'name']; alert on its rate */
  protected abstract readonly failedJobs: { inc(labels: { queue: string; name: string }): void };

  /**
   * Process a job with automatic context propagation and error handling
   */
  protected async processWithContext<T, R>(
    job: Job<T & { _meta?: JobMeta }>,
    handler: (data: T) => Promise<R>
  ): Promise<R> {
    const meta = job.data._meta;
    const correlationId = meta?.correlationId ?? job.id ?? 'unknown';

    const context: RequestContext = {
      correlationId,
      startTime: Date.now(),
      metadata: {
        jobId: job.id,
        jobName: job.name,
        queueName: job.queueName,
        attemptsMade: job.attemptsMade,
      },
    };

    return runWithContext(context, async () => {
      this.logger.log(`Processing job: ${job.name} (${job.id})`);

      try {
        // Remove _meta from data before passing to handler
        const { _meta, ...cleanData } = job.data;
        const result = await handler(cleanData as T);

        const duration = Date.now() - context.startTime;
        this.logger.log(`Job completed: ${job.name} (${job.id}) in ${duration}ms`);

        return result;
      } catch (error) {
        const duration = Date.now() - context.startTime;
        this.logger.error(
          `Job failed: ${job.name} (${job.id}) after ${duration}ms - Attempt ${job.attemptsMade}`,
          error instanceof Error ? error.stack : error
        );
        throw error;
      }
    });
  }

  /**
   * Handle job failure (called when all retries exhausted)
   */
  protected async onFailed(job: Job, error: Error): Promise<void> {
    this.logger.error(
      `Job permanently failed: ${job.name} (${job.id}) after ${job.attemptsMade} attempts`,
      error.stack
    );

    // Terminal failure: record it where an operator will see it (a failed-jobs metric/alert).
    // BullMQ keeps the job in the failed set (bounded by removeOnFail) for inspection and retry.
    this.failedJobs.inc({ queue: job.queueName, name: job.name });
  }

  /**
   * Handle job completion
   */
  protected async onCompleted(job: Job, result: unknown): Promise<void> {
    this.logger.debug(`Job completed callback: ${job.name} (${job.id})`);
  }
}
```
