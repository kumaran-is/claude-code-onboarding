# NestJS Real-World Issues — GitHub & Stack Overflow Reference

Common NestJS framework-level issues sourced from GitHub issues and Stack Overflow, with frequency ratings, root causes, and community-verified solution ordering.

> ORM-specific issues (TypeORM, Mongoose) omitted — workspace uses Prisma 7.x.
> Auth-specific issues (Passport.js) omitted — workspace uses custom JWT with RS256 guards.
> Test-runner issues (Jest) omitted — workspace uses Vitest exclusively. NestJS 12 packages are ESM-only: Jest loads them only on Node >= 24.9 (NestJS migration guide), another reason to stay on Vitest.

---

## DI & Module Resolution Issues

### "Nest can't resolve dependencies of the [Service] (?)"
**Frequency**: HIGHEST (500+ GitHub issues) | **Complexity**: LOW-MEDIUM
**Sources**: GitHub #3186, #886, #2359 | SO 75483101

When encountering this error:
1. Check if provider is in module's `providers` array
2. Verify module `exports` if crossing module boundaries
3. Check for typos in provider names (GitHub #598 — error message can be misleading)
4. **Review import order in barrel exports** — barrel re-exports can cause circular resolution (GitHub #9095)

**Prisma-specific variant**: If the missing provider is `DatabaseService`, ensure `DatabaseModule` is imported AND exports `DatabaseService`.

---

### "Circular dependency detected"
**Frequency**: HIGH | **Complexity**: HIGH
**Sources**: SO 65671318 (32 votes) | Multiple GitHub discussions

Community-proven solutions (in priority order):
1. **Extract shared logic to a third module** — the recommended approach; circular deps usually indicate a design flaw
2. Use `forwardRef()` on BOTH sides of the dependency (not just one)
3. Note: community warns `forwardRef()` can mask deeper architectural issues — prefer extraction

```typescript
// Only use forwardRef as a last resort
@Injectable()
export class UserService {
  constructor(
    @Inject(forwardRef(() => PostService))
    private readonly postService: PostService
  ) {}
}

@Injectable()
export class PostService {
  constructor(
    @Inject(forwardRef(() => UserService))
    private readonly userService: UserService
  ) {}
}
```

---

### "ActorModule exporting itself instead of ActorService"
**Frequency**: MEDIUM | **Complexity**: LOW
**Source**: GitHub #866

The single most common module misconfiguration:

```typescript
// BAD — exports the module, not the service
@Module({
  providers: [ActorService],
  exports: [ActorModule], // ❌ Wrong
})
export class ActorModule {}

// GOOD — export the service so other modules can inject it
@Module({
  providers: [ActorService],
  exports: [ActorService], // ✅ Correct
})
export class ActorModule {}
```

Scan all modules for this pattern: `exports: [SomeModule]` where `SomeModule` is the module being defined.

---

### "Nest can't resolve dependencies of the UserController (?, +)"
**Frequency**: HIGH | **Complexity**: LOW
**Source**: GitHub #886

The `?` and `+` symbols in the error indicate position of missing/found providers:
- `?` = missing provider at this constructor position
- `+` = found provider at this position

**Debug steps**:
1. Count constructor parameters — the `?` position maps 1:1 to parameter index
2. Add the missing service to `module.providers`
3. Verify `@Injectable()` is on the service class

---

### "More informative error message when dependencies are improperly setup"
**Frequency**: N/A | **Complexity**: N/A
**Source**: GitHub #223 (Feature Request — intentional design)

**Why NestJS DI errors are generic**: NestJS intentionally keeps DI error messages generic for security — leaking provider names in production could expose internal architecture.

**Workarounds in development**:
1. Enable verbose logging: `NestFactory.create(AppModule, { logger: ['verbose'] })`
2. Add custom error messages in providers via `@Inject()` tokens
3. Use `nest info` to verify module structure

---

## Testing Issues

### "Cannot test because NestJS doesn't resolve dependencies in test module"
**Frequency**: HIGH | **Complexity**: MEDIUM
**Sources**: SO 75483101, 62942112, 62822943

Proven testing solutions for Vitest + `@nestjs/testing`:
1. Mock every dependency explicitly in `Test.createTestingModule({ providers: [...] })`
2. Use `{ provide: ServiceClass, useValue: mockValue }` pattern — do not rely on auto-wiring in tests
3. Import all required modules in `Test.createTestingModule({ imports: [...] })`
4. For Prisma: use `{ provide: DatabaseService, useValue: mockDatabaseService }` — never connect real DB in unit tests

```typescript
// Vitest + @nestjs/testing pattern
beforeEach(async () => {
  const module = await Test.createTestingModule({
    providers: [
      ServiceUnderTest,
      {
        provide: DatabaseService,    // Prisma wrapper
        useValue: {
          user: { findUnique: vi.fn(), create: vi.fn() },
        },
      },
      {
        provide: ConfigService,
        useValue: { getRequired: vi.fn().mockReturnValue('test-value') },
      },
    ],
  }).compile();

  service = module.get<ServiceUnderTest>(ServiceUnderTest);
});
```

---

## JWT & Auth Issues

### "secretOrPrivateKey must have a value"
**Frequency**: HIGH | **Complexity**: LOW
**Sources**: Multiple community reports

Applies to any JWT implementation (not just Passport):
1. Set `JWT_SECRET` (or your key env var) in `.env` file
2. **Check ConfigModule loads BEFORE JwtModule** — async config loading order matters
3. Verify `.env` file location is the project root (not `src/`)
4. Use fail-fast static config reader — crash at startup if key is missing, not at runtime

```typescript
// Fail-fast pattern — catches missing JWT secret at startup
export const Config = {
  jwtSecret: getEnv('JWT_SECRET'), // throws if missing — no ?? fallback
} as const;
```

---

## Production Issues

### Memory Leaks in Production
**Frequency**: LOW | **Complexity**: HIGH
**Sources**: Community reports

Detection and fixes:
1. Profile with `node --inspect` + Chrome DevTools Memory tab (heap snapshots)
2. **Remove event listeners in `onModuleDestroy()`** — the most common NestJS leak source
3. Close external connections (Redis, HTTP clients) in `onApplicationShutdown()`
4. Monitor heap snapshots over time — look for growing `Array`, `Map`, or `EventEmitter` instances

```typescript
@Injectable()
export class SomeService implements OnModuleDestroy {
  private readonly emitter = new EventEmitter();

  onModuleDestroy() {
    this.emitter.removeAllListeners(); // ✅ Clean up
  }
}
```

---

### Version-Specific Regressions
**Frequency**: LOW | **Complexity**: MEDIUM
**Source**: GitHub #2359 (v6.3.1 regression)

When a working feature breaks after a NestJS version bump:
1. Check GitHub issues filtered by your specific version tag
2. Try downgrading to previous patch version (`@nestjs/core@12.x.y-1`), keeping every `@nestjs/*` core package on the same version
3. Update to latest patch (regressions are usually fixed quickly)
4. Report with a minimal reproduction (required for triage)

---

## `@golevelup/ts-jest` → `@golevelup/nestjs-testing` for Mock Creation

The `createMock<T>()` helper creates fully-typed mocks with auto-mocked methods. Works with Vitest:

```bash
npm install --save-dev -E @golevelup/nestjs-testing@0.1.2
```

```typescript
import { createMock } from '@golevelup/nestjs-testing';
import { DatabaseService } from '../database/database.service.js';

// Auto-creates a mock with all methods as vi.fn()
const mockDb = createMock<DatabaseService>();

// Equivalent to manually typing out every method mock
```

Use when the service has many methods and manual mock setup becomes verbose.
