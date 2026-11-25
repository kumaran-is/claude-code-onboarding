# NestJS Feature Flags

Feature flag evaluation with boolean toggles, percentage rollouts, user/tenant targeting, and scheduled enablement.

## 1. Feature Flags Service

Provides feature flag evaluation with support for boolean toggles, percentage-based rollouts, user/tenant targeting, and scheduled enablement.

### Implementation

```typescript
/**
 * Feature Flags Service
 *
 * Provides feature flag evaluation with support for:
 * - Boolean toggles
 * - Percentage-based rollouts
 * - User/tenant targeting
 * - Scheduled enablement
 */

import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { createHash } from 'crypto';

import { DynamicConfigurationService } from '../../dynamic-configuration/services/dynamic-configuration.service.js';
import { getRequestContext } from '../../../common/context/request-context.service.js';

interface FeatureFlagConfig {
  enabled: boolean;
  percentage?: number;
  targetRules?: {
    userIds?: string[];
    tenantIds?: string[];
    environments?: string[];
  };
  enabledAt?: Date;
  disabledAt?: Date;
}

@Injectable()
export class FeatureFlagsService implements OnModuleInit {
  private readonly logger = new Logger(FeatureFlagsService.name);
  private readonly flagCache = new Map<string, FeatureFlagConfig>();
  private lastRefresh = 0;
  private readonly refreshInterval = 60000; // 1 minute

  constructor(
    private readonly dynamicConfig: DynamicConfigurationService,
  ) {}

  async onModuleInit(): Promise<void> {
    await this.refreshFlags();
  }

  /**
   * Check if a feature flag is enabled
   *
   * @param flagKey - The feature flag key
   * @param context - Optional context for targeted evaluation
   */
  async isEnabled(
    flagKey: string,
    context?: { userId?: string; tenantId?: string }
  ): Promise<boolean> {
    // Refresh cache if stale
    if (Date.now() - this.lastRefresh > this.refreshInterval) {
      await this.refreshFlags();
    }

    const flag = this.flagCache.get(flagKey);

    if (!flag) {
      this.logger.debug(`Feature flag not found: ${flagKey}`);
      return false;
    }

    // Check if globally disabled
    if (!flag.enabled) {
      return false;
    }

    // Check scheduled enablement
    const now = new Date();
    if (flag.enabledAt && now < flag.enabledAt) {
      return false;
    }
    if (flag.disabledAt && now > flag.disabledAt) {
      return false;
    }

    // Get context from request if not provided
    const requestCtx = getRequestContext();
    const userId = context?.userId ?? requestCtx?.userId;
    const tenantId = context?.tenantId ?? requestCtx?.tenantId;

    // Check target rules
    if (flag.targetRules) {
      // User targeting
      if (flag.targetRules.userIds?.length && userId) {
        if (flag.targetRules.userIds.includes(userId)) {
          return true;
        }
      }

      // Tenant targeting
      if (flag.targetRules.tenantIds?.length && tenantId) {
        if (flag.targetRules.tenantIds.includes(tenantId)) {
          return true;
        }
      }

      // Environment targeting
      if (flag.targetRules.environments?.length) {
        const env = process.env.NODE_ENV ?? 'development';
        if (!flag.targetRules.environments.includes(env)) {
          return false;
        }
      }
    }

    // Check percentage rollout
    if (flag.percentage !== undefined && flag.percentage < 100) {
      const identifier = userId ?? tenantId ?? 'anonymous';
      const hash = this.hashIdentifier(flagKey, identifier);
      return hash < flag.percentage;
    }

    return true;
  }

  /**
   * Get all feature flags
   */
  getAllFlags(): Map<string, FeatureFlagConfig> {
    return new Map(this.flagCache);
  }

  /**
   * Refresh flags from database
   */
  @Cron(CronExpression.EVERY_MINUTE)
  async refreshFlags(): Promise<void> {
    try {
      const flags = await this.dynamicConfig.getAllByCategory('feature_flag');

      this.flagCache.clear();
      for (const [key, value] of Object.entries(flags)) {
        this.flagCache.set(key.replace('feature.', ''), value as FeatureFlagConfig);
      }

      this.lastRefresh = Date.now();
      this.logger.debug(`Refreshed ${this.flagCache.size} feature flags`);
    } catch (error) {
      this.logger.error('Failed to refresh feature flags', error);
    }
  }

  /**
   * Hash identifier for percentage rollout
   * Returns a number between 0 and 100
   */
  private hashIdentifier(flagKey: string, identifier: string): number {
    const hash = createHash('sha256')
      .update(`${flagKey}:${identifier}`)
      .digest('hex');

    // Convert first 8 chars of hash to number and mod 100
    const num = parseInt(hash.substring(0, 8), 16);
    return num % 100;
  }
}
```

### Usage

```typescript
// In a controller or service
constructor(
  private readonly featureFlags: FeatureFlagsService
) {}

async getProducts(): Promise<Product[]> {
  // Simple check
  const newSearchEnabled = await this.featureFlags.isEnabled('new-search-algorithm');

  if (newSearchEnabled) {
    return this.productService.searchV2();
  }
  return this.productService.searchV1();
}

// With explicit context
async getUserDashboard(userId: string): Promise<Dashboard> {
  const betaFeaturesEnabled = await this.featureFlags.isEnabled(
    'beta-dashboard',
    { userId }
  );

  return this.dashboardService.getDashboard(userId, betaFeaturesEnabled);
}
```

## 2. Feature Flags with Redis Fallback

For multi-instance deployments, this version uses Redis as a shared cache to ensure consistency across instances, with local cache as fallback when Redis is unavailable.

### Implementation

```typescript
/**
 * Feature Flags Service with Redis Fallback
 *
 * For multi-instance deployments, this version uses Redis
 * as a shared cache to ensure consistency across instances.
 */

import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { createHash } from 'crypto';

import { L2CacheService } from '../../cache/services/l2-cache.service.js';
import { DynamicConfigurationService } from '../../dynamic-configuration/services/dynamic-configuration.service.js';
import { getRequestContext } from '../../../common/context/request-context.service.js';

interface FeatureFlagConfig {
  enabled: boolean;
  percentage?: number;
  targetRules?: {
    userIds?: string[];
    tenantIds?: string[];
    environments?: string[];
  };
  enabledAt?: Date;
  disabledAt?: Date;
}

@Injectable()
export class FeatureFlagsRedisService implements OnModuleInit {
  private readonly logger = new Logger(FeatureFlagsRedisService.name);
  private readonly localCache = new Map<string, FeatureFlagConfig>();
  private readonly CACHE_KEY_PREFIX = 'feature_flags:';
  private readonly CACHE_TTL = 60; // 1 minute
  private lastRefresh = 0;

  constructor(
    private readonly dynamicConfig: DynamicConfigurationService,
    private readonly redisCache: L2CacheService,
  ) {}

  async onModuleInit(): Promise<void> {
    await this.refreshFlags();
  }

  /**
   * Check if a feature flag is enabled
   * Uses Redis for multi-instance consistency with local cache fallback
   */
  async isEnabled(
    flagKey: string,
    context?: { userId?: string; tenantId?: string }
  ): Promise<boolean> {
    // Try Redis first for multi-instance consistency
    let flag = await this.getFlagFromRedis(flagKey);

    // Fallback to local cache if Redis unavailable
    if (!flag) {
      flag = this.localCache.get(flagKey);
    }

    if (!flag) {
      this.logger.debug(`Feature flag not found: ${flagKey}`);
      return false;
    }

    return this.evaluateFlag(flag, flagKey, context);
  }

  private async getFlagFromRedis(flagKey: string): Promise<FeatureFlagConfig | null> {
    try {
      const cached = await this.redisCache.get<FeatureFlagConfig>(
        `${this.CACHE_KEY_PREFIX}${flagKey}`
      );
      return cached ?? null;
    } catch (error) {
      this.logger.warn(`Redis unavailable for feature flag: ${flagKey}`, error);
      return null;
    }
  }

  private evaluateFlag(
    flag: FeatureFlagConfig,
    flagKey: string,
    context?: { userId?: string; tenantId?: string }
  ): boolean {
    if (!flag.enabled) return false;

    const now = new Date();
    if (flag.enabledAt && now < new Date(flag.enabledAt)) return false;
    if (flag.disabledAt && now > new Date(flag.disabledAt)) return false;

    const requestCtx = getRequestContext();
    const userId = context?.userId ?? requestCtx?.userId;
    const tenantId = context?.tenantId ?? requestCtx?.tenantId;

    // Check targeting rules
    if (flag.targetRules) {
      if (flag.targetRules.userIds?.includes(userId ?? '')) return true;
      if (flag.targetRules.tenantIds?.includes(tenantId ?? '')) return true;
      if (flag.targetRules.environments?.length) {
        const env = process.env.NODE_ENV ?? 'development';
        if (!flag.targetRules.environments.includes(env)) return false;
      }
    }

    // Percentage rollout
    if (flag.percentage !== undefined && flag.percentage < 100) {
      const identifier = userId ?? tenantId ?? 'anonymous';
      const hash = this.hashIdentifier(flagKey, identifier);
      return hash < flag.percentage;
    }

    return true;
  }

  @Cron(CronExpression.EVERY_MINUTE)
  async refreshFlags(): Promise<void> {
    try {
      const flags = await this.dynamicConfig.getAllByCategory('feature_flag');

      // Update both local cache and Redis
      for (const [key, value] of Object.entries(flags)) {
        const flagKey = key.replace('feature.', '');
        const flagConfig = value as FeatureFlagConfig;

        this.localCache.set(flagKey, flagConfig);

        // Update Redis for multi-instance consistency
        try {
          await this.redisCache.set(
            `${this.CACHE_KEY_PREFIX}${flagKey}`,
            flagConfig,
            this.CACHE_TTL
          );
        } catch (error) {
          this.logger.warn(`Failed to update Redis for flag: ${flagKey}`);
        }
      }

      this.lastRefresh = Date.now();
      this.logger.debug(`Refreshed ${this.localCache.size} feature flags`);
    } catch (error) {
      this.logger.error('Failed to refresh feature flags', error);
    }
  }

  private hashIdentifier(flagKey: string, identifier: string): number {
    const hash = createHash('sha256')
      .update(`${flagKey}:${identifier}`)
      .digest('hex');
    return parseInt(hash.substring(0, 8), 16) % 100;
  }
}
```

### Module Configuration

```typescript
import { Module } from '@nestjs/common';
import { ScheduleModule } from '@nestjs/schedule';
import { FeatureFlagsRedisService } from './feature-flags-redis.service.js';
import { L2CacheService } from '../../cache/services/l2-cache.service.js';
import { DynamicConfigurationService } from '../../dynamic-configuration/services/dynamic-configuration.service.js';

@Module({
  imports: [ScheduleModule.forRoot()],
  providers: [
    FeatureFlagsRedisService,
    L2CacheService,
    DynamicConfigurationService,
  ],
  exports: [FeatureFlagsRedisService],
})
export class FeatureFlagsModule {}
```

## 3. Best Practices

### Feature Flags
- Use percentage rollout for gradual feature releases (10% → 25% → 50% → 100%)
- Target specific users/tenants for beta testing before full rollout
- Schedule feature enablement using `enabledAt`/`disabledAt` for time-based releases
- Use Redis-backed version in multi-instance deployments for consistency
- Always provide default behavior when flag evaluation fails

### Common Patterns

#### Gradual Rollout
```typescript
// Start with 10% of users
await featureFlags.isEnabled('new-checkout-flow'); // 10% true

// After monitoring, increase to 50%
// Then 100% when stable
```

#### Beta Testing
```typescript
const config = {
  enabled: true,
  targetRules: {
    userIds: ['beta-tester-1', 'beta-tester-2'],
    environments: ['staging', 'production'],
  }
};
```

#### Scheduled Release
```typescript
const config = {
  enabled: true,
  enabledAt: new Date('2024-12-01T00:00:00Z'),
  disabledAt: new Date('2024-12-31T23:59:59Z'),
};
```

#### A/B Testing
```typescript
const variant = await featureFlags.isEnabled('checkout-variant-a')
  ? 'variant-a'
  : 'variant-b';

return this.checkoutService.render(variant);
```
