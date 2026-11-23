# NestJS Messaging — RabbitMQ for Reliable Messaging

Reliable messaging patterns using RabbitMQ (AMQP) for cross-service communication.

## RabbitMQ — Reliable Messaging

### Module Configuration

```typescript
/**
 * RabbitMQ Messaging Module
 *
 * Use this module when you need:
 * - Guaranteed message delivery with ACKs
 * - Complex routing patterns (fanout, topic, headers)
 * - Cross-language microservices communication
 * - RPC-style request/response patterns
 * - Mission-critical messaging with DLQs
 */

import { Module, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { RabbitMQModule as GolevelupRabbitMQ } from '@golevelup/nestjs-rabbitmq';

// Exchange names for different routing patterns
export const EXCHANGES = {
  DIRECT: 'app.direct',
  TOPIC: 'app.topic',
  FANOUT: 'app.fanout',
  DEAD_LETTER: 'app.dlx',
} as const;

// Queue names
export const QUEUES = {
  EMAIL: 'email.queue',
  NOTIFICATIONS: 'notifications.queue',
  WEBHOOKS: 'webhooks.queue',
  DEAD_LETTER: 'dead-letter.queue',
} as const;

// Routing keys for topic exchange
export const ROUTING_KEYS = {
  EMAIL_SEND: 'email.send',
  EMAIL_BULK: 'email.bulk',
  NOTIFICATION_PUSH: 'notification.push',
  NOTIFICATION_SMS: 'notification.sms',
  WEBHOOK_OUTGOING: 'webhook.outgoing',
} as const;

@Module({
  imports: [
    GolevelupRabbitMQ.forRootAsync(GolevelupRabbitMQ, {
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        uri: config.getOrThrow<string>('RABBITMQ_URI'),
        connectionInitOptions: {
          wait: true,
          timeout: 30000,
        },
        connectionManagerOptions: {
          heartbeatIntervalInSeconds: 30,
          reconnectTimeInSeconds: 5,
        },
        exchanges: [
          { name: EXCHANGES.DIRECT, type: 'direct', options: { durable: true } },
          { name: EXCHANGES.TOPIC, type: 'topic', options: { durable: true } },
          { name: EXCHANGES.FANOUT, type: 'fanout', options: { durable: true } },
          { name: EXCHANGES.DEAD_LETTER, type: 'direct', options: { durable: true } },
        ],
        queues: [
          {
            name: QUEUES.EMAIL,
            options: {
              durable: true,
              arguments: {
                'x-dead-letter-exchange': EXCHANGES.DEAD_LETTER,
                'x-dead-letter-routing-key': QUEUES.DEAD_LETTER,
              },
            },
          },
          {
            name: QUEUES.NOTIFICATIONS,
            options: {
              durable: true,
              arguments: {
                'x-dead-letter-exchange': EXCHANGES.DEAD_LETTER,
                'x-dead-letter-routing-key': QUEUES.DEAD_LETTER,
              },
            },
          },
          {
            name: QUEUES.WEBHOOKS,
            options: {
              durable: true,
              arguments: {
                'x-dead-letter-exchange': EXCHANGES.DEAD_LETTER,
                'x-dead-letter-routing-key': QUEUES.DEAD_LETTER,
              },
            },
          },
          {
            name: QUEUES.DEAD_LETTER,
            options: { durable: true },
          },
        ],
        enableControllerDiscovery: true,
        prefetchCount: 10,
      }),
    }),
  ],
  exports: [GolevelupRabbitMQ],
})
export class RabbitMQModule implements OnModuleInit {
  private readonly logger = new Logger(RabbitMQModule.name);

  onModuleInit(): void {
    this.logger.log('RabbitMQ Module initialized');
    this.logger.log(`Exchanges: ${Object.values(EXCHANGES).join(', ')}`);
    this.logger.log(`Queues: ${Object.values(QUEUES).join(', ')}`);
  }
}
```

### Publisher Service

```typescript
/**
 * RabbitMQ Publisher Service
 *
 * Single orchestrator for publishing messages to RabbitMQ.
 * Supports direct, topic, and fanout exchange patterns.
 */

import { Injectable, Logger } from '@nestjs/common';
import { AmqpConnection } from '@golevelup/nestjs-rabbitmq';
import { EXCHANGES, ROUTING_KEYS } from '../rabbitmq.module';
import { getCorrelationId } from '../../../../common/context/request-context.service';

export interface PublishOptions {
  correlationId?: string;
  replyTo?: string;
  expiration?: string;
  priority?: number;
  persistent?: boolean;
  headers?: Record<string, string>;
}

@Injectable()
export class RabbitMQPublisherService {
  private readonly logger = new Logger(RabbitMQPublisherService.name);

  constructor(private readonly amqpConnection: AmqpConnection) {}

  /**
   * Publish to direct exchange (point-to-point)
   */
  async publishDirect<T>(
    routingKey: string,
    message: T,
    options?: PublishOptions
  ): Promise<void> {
    await this.publish(EXCHANGES.DIRECT, routingKey, message, options);
  }

  /**
   * Publish to topic exchange (pattern-based routing)
   */
  async publishTopic<T>(
    routingKey: string,
    message: T,
    options?: PublishOptions
  ): Promise<void> {
    await this.publish(EXCHANGES.TOPIC, routingKey, message, options);
  }

  /**
   * Publish to fanout exchange (broadcast to all)
   */
  async broadcast<T>(message: T, options?: PublishOptions): Promise<void> {
    await this.publish(EXCHANGES.FANOUT, '', message, options);
  }

  /**
   * RPC-style request/response
   */
  async request<TRequest, TResponse>(
    routingKey: string,
    message: TRequest,
    timeout = 30000
  ): Promise<TResponse> {
    const correlationId = getCorrelationId() ?? crypto.randomUUID();

    this.logger.debug(`RPC request: ${routingKey} - correlationId: ${correlationId}`);

    const response = await this.amqpConnection.request<TResponse>({
      exchange: EXCHANGES.DIRECT,
      routingKey,
      payload: message,
      timeout,
      correlationId,
    });

    return response;
  }

  /**
   * Send email (convenience method)
   */
  async sendEmail(payload: {
    to: string | string[];
    subject: string;
    template: string;
    data: Record<string, unknown>;
  }): Promise<void> {
    await this.publishTopic(ROUTING_KEYS.EMAIL_SEND, payload);
  }

  /**
   * Send notification (convenience method)
   */
  async sendNotification(payload: {
    userId: string;
    type: 'push' | 'sms' | 'in-app';
    title: string;
    body: string;
    data?: Record<string, unknown>;
  }): Promise<void> {
    const routingKey = payload.type === 'push'
      ? ROUTING_KEYS.NOTIFICATION_PUSH
      : ROUTING_KEYS.NOTIFICATION_SMS;
    await this.publishTopic(routingKey, payload);
  }

  /**
   * Dispatch webhook (convenience method)
   */
  async dispatchWebhook(payload: {
    url: string;
    event: string;
    data: Record<string, unknown>;
    headers?: Record<string, string>;
  }): Promise<void> {
    await this.publishTopic(ROUTING_KEYS.WEBHOOK_OUTGOING, payload, {
      persistent: true,
      priority: 5,
    });
  }

  private async publish<T>(
    exchange: string,
    routingKey: string,
    message: T,
    options?: PublishOptions
  ): Promise<void> {
    const correlationId = options?.correlationId ?? getCorrelationId() ?? 'unknown';

    const enrichedMessage = {
      ...message,
      _meta: {
        correlationId,
        publishedAt: new Date().toISOString(),
        exchange,
        routingKey,
      },
    };

    await this.amqpConnection.publish(exchange, routingKey, enrichedMessage, {
      correlationId,
      persistent: options?.persistent ?? true,
      priority: options?.priority,
      expiration: options?.expiration,
      headers: options?.headers,
    });

    this.logger.debug(
      `Message published: ${exchange}/${routingKey} - correlationId: ${correlationId}`
    );
  }
}
```

### Consumer Handler

```typescript
/**
 * Email Consumer Handler
 *
 * Example of a RabbitMQ message consumer with:
 * - Automatic ACK/NACK handling
 * - Dead letter queue on failure
 * - Correlation ID propagation
 */

import { Injectable, Logger } from '@nestjs/common';
import { RabbitSubscribe, Nack } from '@golevelup/nestjs-rabbitmq';
import { EXCHANGES, QUEUES, ROUTING_KEYS } from '../rabbitmq.module';
import { runWithContext, RequestContext } from '../../../../common/context/request-context.service';
import { EmailService } from '../../../email/email.service';

interface EmailMessage {
  to: string | string[];
  subject: string;
  template: string;
  data: Record<string, unknown>;
  _meta?: {
    correlationId: string;
    publishedAt: string;
  };
}

@Injectable()
export class EmailHandler {
  private readonly logger = new Logger(EmailHandler.name);

  constructor(private readonly emailService: EmailService) {}

  @RabbitSubscribe({
    exchange: EXCHANGES.TOPIC,
    routingKey: ROUTING_KEYS.EMAIL_SEND,
    queue: QUEUES.EMAIL,
    queueOptions: {
      durable: true,
    },
  })
  async handleEmailSend(message: EmailMessage): Promise<void | Nack> {
    const correlationId = message._meta?.correlationId ?? 'unknown';

    const context: RequestContext = {
      correlationId,
      startTime: Date.now(),
      metadata: {
        handler: 'EmailHandler.handleEmailSend',
        queue: QUEUES.EMAIL,
      },
    };

    return runWithContext(context, async () => {
      this.logger.log(`Processing email: ${message.subject} to ${message.to}`);

      try {
        await this.emailService.send(message);

        const duration = Date.now() - context.startTime;
        this.logger.log(`Email sent successfully in ${duration}ms`);

        // Return void to ACK the message
        return;
      } catch (error) {
        this.logger.error(
          `Failed to send email: ${message.subject}`,
          error instanceof Error ? error.stack : error
        );

        // NACK and requeue (will go to DLQ after max retries)
        return new Nack(false); // false = don't requeue, send to DLQ
      }
    });
  }

  @RabbitSubscribe({
    exchange: EXCHANGES.TOPIC,
    routingKey: ROUTING_KEYS.EMAIL_BULK,
    queue: QUEUES.EMAIL,
  })
  async handleBulkEmail(message: EmailMessage): Promise<void | Nack> {
    // Similar pattern for bulk email processing
    this.logger.log(`Processing bulk email: ${message.subject}`);
    return;
  }
}
```
