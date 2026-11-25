# NestJS Messaging — Kafka for Event Streaming

High-throughput event streaming patterns using Apache Kafka for analytics and event sourcing.

## Kafka — Event Streaming

### Module Configuration

```typescript
/**
 * Kafka Streaming Module
 *
 * Use this module when you need:
 * - High-throughput event streaming (1M+ events/day)
 * - Event sourcing with replay capability
 * - Real-time analytics and data pipelines
 * - Log aggregation across services
 * - Exactly-once delivery semantics
 */

import { Module, Logger, OnModuleInit, OnModuleDestroy, Inject } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Kafka, Consumer, Producer, Admin, logLevel } from 'kafkajs';

// Topic names
export const TOPICS = {
  USER_EVENTS: 'user-events',
  ORDER_EVENTS: 'order-events',
  ANALYTICS_EVENTS: 'analytics-events',
  AUDIT_LOG: 'audit-log',
  DEAD_LETTER: 'dead-letter',
} as const;

// Consumer group IDs
export const CONSUMER_GROUPS = {
  USER_SERVICE: 'user-service-group',
  ORDER_SERVICE: 'order-service-group',
  ANALYTICS_SERVICE: 'analytics-service-group',
} as const;

@Module({
  providers: [
    {
      provide: 'KAFKA_CLIENT',
      inject: [ConfigService],
      useFactory: (config: ConfigService) => {
        // src/config/env.ts: KAFKA_BROKERS: z.string().min(1) (required), KAFKA_CLIENT_ID: z.string().default('nestjs-app'),
        // KAFKA_SSL: z.stringbool().default(false). ConfigService returns the validated, typed values.
        return new Kafka({
          clientId: config.getOrThrow<string>('KAFKA_CLIENT_ID'),
          brokers: config.getOrThrow<string>('KAFKA_BROKERS').split(','),
          ssl: config.getOrThrow<boolean>('KAFKA_SSL'),
          sasl: config.get<string>('KAFKA_SASL_USERNAME')
            ? {
                mechanism: 'plain',
                username: config.getOrThrow<string>('KAFKA_SASL_USERNAME'),
                password: config.getOrThrow<string>('KAFKA_SASL_PASSWORD'),
              }
            : undefined,
          logLevel: logLevel.INFO,
          retry: {
            initialRetryTime: 100,
            retries: 8,
          },
        });
      },
    },
    {
      provide: 'KAFKA_PRODUCER',
      inject: ['KAFKA_CLIENT'],
      useFactory: async (kafka: Kafka) => {
        const producer = kafka.producer({
          allowAutoTopicCreation: false,
          idempotent: true, // Exactly-once semantics
          maxInFlightRequests: 5,
        });
        await producer.connect();
        return producer;
      },
    },
    {
      provide: 'KAFKA_ADMIN',
      inject: ['KAFKA_CLIENT'],
      useFactory: async (kafka: Kafka) => {
        const admin = kafka.admin();
        await admin.connect();
        return admin;
      },
    },
  ],
  exports: ['KAFKA_CLIENT', 'KAFKA_PRODUCER', 'KAFKA_ADMIN'],
})
export class KafkaModule implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(KafkaModule.name);

  constructor(
    @Inject('KAFKA_ADMIN') private readonly admin: Admin,
  ) {}

  async onModuleInit(): Promise<void> {
    this.logger.log('Kafka Module initializing...');
    await this.ensureTopicsExist();
    this.logger.log('Kafka Module initialized');
  }

  async onModuleDestroy(): Promise<void> {
    await this.admin.disconnect();
    this.logger.log('Kafka Admin disconnected');
  }

  private async ensureTopicsExist(): Promise<void> {
    const existingTopics = await this.admin.listTopics();

    const topicsToCreate = Object.values(TOPICS)
      .filter((topic) => !existingTopics.includes(topic))
      .map((topic) => ({
        topic,
        numPartitions: topic === TOPICS.ANALYTICS_EVENTS ? 12 : 6, // More partitions for high-volume
        replicationFactor: 3,
        configEntries: [
          { name: 'retention.ms', value: '604800000' }, // 7 days
          { name: 'cleanup.policy', value: topic === TOPICS.AUDIT_LOG ? 'compact' : 'delete' },
        ],
      }));

    if (topicsToCreate.length > 0) {
      await this.admin.createTopics({ topics: topicsToCreate });
      this.logger.log(`Created topics: ${topicsToCreate.map((t) => t.topic).join(', ')}`);
    }
  }
}
```

### Producer Service

```typescript
/**
 * Kafka Producer Service
 *
 * Single orchestrator for publishing events to Kafka topics.
 * Supports batching, partitioning, and exactly-once semantics.
 */

import { Injectable, Inject, Logger, OnModuleDestroy } from '@nestjs/common';
import { Producer, CompressionTypes, Message } from 'kafkajs';
import { TOPICS } from '../kafka.module.js';
import { getCorrelationId, getRequestContext } from '../../../../common/context/request-context.service.js';

export interface KafkaEvent<T = unknown> {
  key?: string;
  value: T;
  headers?: Record<string, string>;
  partition?: number;
  timestamp?: string;
}

export interface PublishOptions {
  partition?: number;
  key?: string;
  headers?: Record<string, string>;
  compression?: CompressionTypes;
}

@Injectable()
export class KafkaProducerService implements OnModuleDestroy {
  private readonly logger = new Logger(KafkaProducerService.name);

  constructor(@Inject('KAFKA_PRODUCER') private readonly producer: Producer) {}

  async onModuleDestroy(): Promise<void> {
    await this.producer.disconnect();
    this.logger.log('Kafka Producer disconnected');
  }

  /**
   * Publish a single event to a topic
   */
  async publish<T>(
    topic: string,
    event: T,
    options?: PublishOptions
  ): Promise<void> {
    const correlationId = getCorrelationId() ?? crypto.randomUUID();
    const context = getRequestContext();

    const message: Message = {
      key: options?.key ?? null,
      value: JSON.stringify({
        ...event,
        _meta: {
          correlationId,
          publishedAt: new Date().toISOString(),
          userId: context?.userId,
          tenantId: context?.tenantId,
        },
      }),
      headers: {
        'correlation-id': correlationId,
        'content-type': 'application/json',
        ...options?.headers,
      },
      partition: options?.partition,
      timestamp: Date.now().toString(),
    };

    await this.producer.send({
      topic,
      messages: [message],
      compression: options?.compression ?? CompressionTypes.GZIP,
    });

    this.logger.debug(`Event published: ${topic} - correlationId: ${correlationId}`);
  }

  /**
   * Publish multiple events in a batch (high throughput)
   */
  async publishBatch<T>(
    topic: string,
    events: KafkaEvent<T>[]
  ): Promise<void> {
    const correlationId = getCorrelationId() ?? crypto.randomUUID();

    const messages: Message[] = events.map((event, index) => ({
      key: event.key ?? null,
      value: JSON.stringify({
        ...event.value,
        _meta: {
          correlationId,
          batchIndex: index,
          publishedAt: new Date().toISOString(),
        },
      }),
      headers: {
        'correlation-id': correlationId,
        'batch-size': events.length.toString(),
        ...event.headers,
      },
      partition: event.partition,
      timestamp: event.timestamp ?? Date.now().toString(),
    }));

    await this.producer.send({
      topic,
      messages,
      compression: CompressionTypes.GZIP,
    });

    this.logger.debug(`Batch published: ${topic} (${events.length} events) - correlationId: ${correlationId}`);
  }

  /**
   * Publish user event (convenience method)
   */
  async publishUserEvent(event: {
    userId: string;
    eventType: string;
    data: Record<string, unknown>;
  }): Promise<void> {
    await this.publish(TOPICS.USER_EVENTS, event, {
      key: event.userId, // Partition by user ID for ordering
    });
  }

  /**
   * Publish order event (convenience method)
   */
  async publishOrderEvent(event: {
    orderId: string;
    eventType: string;
    data: Record<string, unknown>;
  }): Promise<void> {
    await this.publish(TOPICS.ORDER_EVENTS, event, {
      key: event.orderId,
    });
  }

  /**
   * Publish analytics event (convenience method)
   */
  async publishAnalyticsEvent(event: {
    eventName: string;
    properties: Record<string, unknown>;
    userId?: string;
    sessionId?: string;
  }): Promise<void> {
    await this.publish(TOPICS.ANALYTICS_EVENTS, event);
  }

  /**
   * Publish audit log entry (convenience method)
   */
  async publishAuditLog(entry: {
    action: string;
    resourceType: string;
    resourceId: string;
    userId: string;
    changes?: Record<string, { old: unknown; new: unknown }>;
  }): Promise<void> {
    await this.publish(TOPICS.AUDIT_LOG, entry, {
      key: `${entry.resourceType}:${entry.resourceId}`, // Compaction key
    });
  }
}
```

### Consumer Service

```typescript
/**
 * Kafka Consumer Service
 *
 * Base consumer with automatic offset management,
 * error handling, and dead letter queue support.
 */

import { Injectable, Inject, Logger, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { Kafka, Consumer, EachMessagePayload } from 'kafkajs';
import { TOPICS, CONSUMER_GROUPS } from '../kafka.module.js';
import { KafkaProducerService } from './kafka-producer.service.js';
import { runWithContext, RequestContext } from '../../../../common/context/request-context.service.js';

export interface MessageHandler<T = unknown> {
  (payload: T, metadata: MessageMetadata): Promise<void>;
}

export interface MessageMetadata {
  topic: string;
  partition: number;
  offset: string;
  timestamp: string;
  correlationId: string;
}

@Injectable()
export class KafkaConsumerService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(KafkaConsumerService.name);
  private consumer: Consumer;
  private handlers = new Map<string, MessageHandler>();

  constructor(
    @Inject('KAFKA_CLIENT') private readonly kafka: Kafka,
    private readonly producer: KafkaProducerService,
  ) {}

  async onModuleInit(): Promise<void> {
    this.consumer = this.kafka.consumer({
      groupId: CONSUMER_GROUPS.USER_SERVICE,
      sessionTimeout: 30000,
      heartbeatInterval: 3000,
      maxBytesPerPartition: 1048576, // 1MB
      retry: {
        retries: 5,
      },
    });

    await this.consumer.connect();
    this.logger.log('Kafka Consumer connected');
  }

  async onModuleDestroy(): Promise<void> {
    await this.consumer.disconnect();
    this.logger.log('Kafka Consumer disconnected');
  }

  /**
   * Subscribe to a topic with a handler
   */
  async subscribe<T>(
    topic: string,
    handler: MessageHandler<T>,
    options?: { fromBeginning?: boolean }
  ): Promise<void> {
    this.handlers.set(topic, handler as MessageHandler);

    await this.consumer.subscribe({
      topic,
      fromBeginning: options?.fromBeginning ?? false,
    });

    this.logger.log(`Subscribed to topic: ${topic}`);
  }

  /**
   * Start consuming messages
   */
  async startConsuming(): Promise<void> {
    await this.consumer.run({
      eachMessage: async (payload: EachMessagePayload) => {
        await this.handleMessage(payload);
      },
    });
  }

  private async handleMessage(payload: EachMessagePayload): Promise<void> {
    const { topic, partition, message } = payload;
    const handler = this.handlers.get(topic);

    if (!handler) {
      this.logger.warn(`No handler registered for topic: ${topic}`);
      return;
    }

    const correlationId =
      message.headers?.['correlation-id']?.toString() ?? 'unknown';

    const context: RequestContext = {
      correlationId,
      startTime: Date.now(),
      metadata: {
        topic,
        partition,
        offset: message.offset,
      },
    };

    await runWithContext(context, async () => {
      try {
        const value = JSON.parse(message.value?.toString() ?? '{}');

        const metadata: MessageMetadata = {
          topic,
          partition,
          offset: message.offset,
          timestamp: message.timestamp,
          correlationId,
        };

        this.logger.debug(`Processing message: ${topic}[${partition}]@${message.offset}`);

        await handler(value, metadata);

        const duration = Date.now() - context.startTime;
        this.logger.debug(`Message processed in ${duration}ms`);
      } catch (error) {
        this.logger.error(
          `Failed to process message: ${topic}[${partition}]@${message.offset}`,
          error instanceof Error ? error.stack : error
        );

        // Send to dead letter topic
        await this.sendToDeadLetter(topic, message, error);
      }
    });
  }

  private async sendToDeadLetter(
    originalTopic: string,
    message: unknown,
    error: unknown
  ): Promise<void> {
    try {
      await this.producer.publish(TOPICS.DEAD_LETTER, {
        originalTopic,
        originalMessage: message.value?.toString(),
        error: error instanceof Error ? error.message : String(error),
        failedAt: new Date().toISOString(),
      });

      this.logger.warn(`Message sent to dead letter queue from ${originalTopic}`);
    } catch (dlqError) {
      this.logger.error('Failed to send to dead letter queue', dlqError);
    }
  }
}
```
