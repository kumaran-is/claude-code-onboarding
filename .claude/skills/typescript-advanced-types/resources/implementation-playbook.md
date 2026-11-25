# TypeScript Advanced Types Implementation Playbook

This file contains detailed patterns, checklists, and code samples referenced by the skill.

# TypeScript Advanced Types

Comprehensive guidance for mastering TypeScript's advanced type system including generics, conditional types, mapped types, template literal types, and utility types for building robust, type-safe applications.

## When to Use This Skill

- Building type-safe libraries or frameworks
- Creating reusable generic components
- Implementing complex type inference logic
- Designing type-safe API clients
- Building form validation systems
- Creating strongly-typed configuration objects
- Implementing type-safe state management
- Migrating JavaScript codebases to TypeScript

## Core Concepts

### 1. Generics

**Purpose:** Create reusable, type-flexible components while maintaining type safety.

**Basic Generic Function:**
```typescript
function identity<T>(value: T): T {
  return value;
}

const num = identity<number>(42);        // Type: number
const str = identity<string>("hello");    // Type: string
const auto = identity(true);              // Type inferred: boolean
```

**Generic Constraints:**
```typescript
interface HasLength {
  length: number;
}

function logLength<T extends HasLength>(item: T): T {
  console.log(item.length);
  return item;
}

logLength("hello");           // OK: string has length
logLength([1, 2, 3]);         // OK: array has length
logLength({ length: 10 });    // OK: object has length
// logLength(42);             // Error: number has no length
```

**Multiple Type Parameters:**
```typescript
function merge<T, U>(obj1: T, obj2: U): T & U {
  return { ...obj1, ...obj2 };
}

const merged = merge(
  { name: "John" },
  { age: 30 }
);
// Type: { name: string } & { age: number }
```

### 2. Conditional Types

**Purpose:** Create types that depend on conditions, enabling sophisticated type logic.

**Basic Conditional Type:**
```typescript
type IsString<T> = T extends string ? true : false;

type A = IsString<string>;    // true
type B = IsString<number>;    // false
```

**Extracting Return Types:**
```typescript
type ReturnType<T> = T extends (...args: never[]) => infer R ? R : never; // never[]: matches every parameter list without any

function getUser() {
  return { id: 1, name: "John" };
}

type User = ReturnType<typeof getUser>;
// Type: { id: number; name: string; }
```

**Distributive Conditional Types:**
```typescript
type ToArray<T> = T extends any ? T[] : never;

type StrOrNumArray = ToArray<string | number>;
// Type: string[] | number[]
```

**Nested Conditions:**
```typescript
type TypeName<T> =
  T extends string ? "string" :
  T extends number ? "number" :
  T extends boolean ? "boolean" :
  T extends undefined ? "undefined" :
  T extends Function ? "function" :
  "object";

type T1 = TypeName<string>;     // "string"
type T2 = TypeName<() => void>; // "function"
```

### 3. Mapped Types

**Purpose:** Transform existing types by iterating over their properties.

**Basic Mapped Type:**
```typescript
type Readonly<T> = {
  readonly [P in keyof T]: T[P];
};

interface User {
  id: number;
  name: string;
}

type ReadonlyUser = Readonly<User>;
// Type: { readonly id: number; readonly name: string; }
```

**Optional Properties:**
```typescript
type Partial<T> = {
  [P in keyof T]?: T[P];
};

type PartialUser = Partial<User>;
// Type: { id?: number; name?: string; }
```

**Key Remapping:**
```typescript
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K]
};

interface Person {
  name: string;
  age: number;
}

type PersonGetters = Getters<Person>;
// Type: { getName: () => string; getAge: () => number; }
```

**Filtering Properties:**
```typescript
type PickByType<T, U> = {
  [K in keyof T as T[K] extends U ? K : never]: T[K]
};

interface Mixed {
  id: number;
  name: string;
  age: number;
  active: boolean;
}

type OnlyNumbers = PickByType<Mixed, number>;
// Type: { id: number; age: number; }
```

### 4. Template Literal Types

**Purpose:** Create string-based types with pattern matching and transformation.

**Basic Template Literal:**
```typescript
type EventName = "click" | "focus" | "blur";
type EventHandler = `on${Capitalize<EventName>}`;
// Type: "onClick" | "onFocus" | "onBlur"
```

**String Manipulation:**
```typescript
type UppercaseGreeting = Uppercase<"hello">;  // "HELLO"
type LowercaseGreeting = Lowercase<"HELLO">;  // "hello"
type CapitalizedName = Capitalize<"john">;    // "John"
type UncapitalizedName = Uncapitalize<"John">; // "john"
```

**Path Building:**
```typescript
type Path<T> = T extends object
  ? { [K in keyof T]: K extends string
      ? `${K}` | `${K}.${Path<T[K]>}`
      : never
    }[keyof T]
  : never;

interface Config {
  server: {
    host: string;
    port: number;
  };
  database: {
    url: string;
  };
}

type ConfigPath = Path<Config>;
// Type: "server" | "database" | "server.host" | "server.port" | "database.url"
```

### 5. Utility Types

**Built-in Utility Types:**

```typescript
// Partial<T> - Make all properties optional
type PartialUser = Partial<User>;

// Required<T> - Make all properties required
type RequiredUser = Required<PartialUser>;

// Readonly<T> - Make all properties readonly
type ReadonlyUser = Readonly<User>;

// Pick<T, K> - Select specific properties
type UserName = Pick<User, "name" | "email">;

// Omit<T, K> - Remove specific properties
type UserWithoutPassword = Omit<User, "password">;

// Exclude<T, U> - Exclude types from union
type T1 = Exclude<"a" | "b" | "c", "a">;  // "b" | "c"

// Extract<T, U> - Extract types from union
type T2 = Extract<"a" | "b" | "c", "a" | "b">;  // "a" | "b"

// NonNullable<T> - Exclude null and undefined
type T3 = NonNullable<string | null | undefined>;  // string

// Record<K, T> - Create object type with keys K and values T
type PageInfo = Record<"home" | "about", { title: string }>;
```

## Advanced Patterns

### Pattern 1: Type-Safe Event Emitter

```typescript
type EventMap = {
  "user:created": { id: string; name: string };
  "user:updated": { id: string };
  "user:deleted": { id: string };
};

class TypedEventEmitter<T extends Record<string, unknown>> {
  private listeners: {
    [K in keyof T]?: Array<(data: T[K]) => void>;
  } = {};

  on<K extends keyof T>(event: K, callback: (data: T[K]) => void): void {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event]!.push(callback);
  }

  emit<K extends keyof T>(event: K, data: T[K]): void {
    const callbacks = this.listeners[event];
    if (callbacks) {
      callbacks.forEach(callback => callback(data));
    }
  }
}

const emitter = new TypedEventEmitter<EventMap>();

emitter.on("user:created", (data) => {
  console.log(data.id, data.name);  // Type-safe!
});

emitter.emit("user:created", { id: "1", name: "John" });
// emitter.emit("user:created", { id: "1" });  // Error: missing 'name'
```

### Pattern 2: Type-Safe API Client

```typescript
interface User {
  id: string;
  name: string;
  email: string;
}

type HTTPMethod = "GET" | "POST" | "PUT" | "DELETE";

/** One endpoint: params and body are optional; response is what the server returns. */
interface EndpointSpec {
  params?: object;
  body?: unknown;
  response: unknown;
}

type EndpointConfig = {
  "/users": {
    GET: { response: User[] };
    POST: { body: { name: string; email: string }; response: User };
  };
  "/users/:id": {
    GET: { params: { id: string }; response: User };
    PUT: { params: { id: string }; body: Partial<User>; response: User };
    DELETE: { params: { id: string }; response: void };
  };
};

type ExtractParams<T> = T extends { params: infer P } ? P : never;
type ExtractBody<T> = T extends { body: infer B } ? B : never;
type ExtractResponse<T> = T extends { response: infer R } ? R : never;

// [X] extends [never]: the tuple wrap stops distribution, so "no params" is detected reliably.
type RequestOptions<E> =
  [ExtractParams<E>] extends [never]
    ? [ExtractBody<E>] extends [never]
      ? []
      : [options: { body: ExtractBody<E> }]
    : [ExtractBody<E>] extends [never]
      ? [options: { params: ExtractParams<E> }]
      : [options: { params: ExtractParams<E>; body: ExtractBody<E> }];

// Each path maps only the methods it supports (Partial), and every method must match EndpointSpec.
class APIClient<Config extends { [Path in keyof Config]: Partial<Record<HTTPMethod, EndpointSpec>> }> {
  async request<Path extends keyof Config & string, Method extends keyof Config[Path] & HTTPMethod>(
    path: Path,
    method: Method,
    ...options: RequestOptions<Config[Path][Method]>
  ): Promise<ExtractResponse<Config[Path][Method]>> {
    // Type-level example: the transport is out of scope. A real client fetches, then parses the body with the
    // endpoint's schema (Boundaries rule 1) instead of asserting the type.
    throw new Error(`APIClient.request ${method} ${path}: transport not implemented in this example (${options.length} options)`);
  }
}

const api = new APIClient<EndpointConfig>();

// Type-safe API calls (the transport throws in this example, so they are wrapped in a function).
export async function examples(): Promise<void> {
  const users: User[] = await api.request("/users", "GET");
  const newUser: User = await api.request("/users", "POST", { body: { name: "John", email: "john@example.com" } });
  const user: User = await api.request("/users/:id", "GET", { params: { id: "123" } });
  // @ts-expect-error DELETE is not defined for "/users"
  await api.request("/users", "DELETE");
  // @ts-expect-error POST needs a body
  await api.request("/users", "POST");
  // @ts-expect-error params.id must be a string
  await api.request("/users/:id", "GET", { params: { id: 123 } });
  void [users, newUser, user];
}
```

The `response` types above are compile-time promises only: the implementation must parse each body with a schema before returning it (see "Boundaries" in `../SKILL.md`), otherwise any payload is accepted.

### Pattern 3: Builder Pattern with Type Safety

```typescript
// Keys whose property is not optional.
type RequiredKeys<T> = {
  [K in keyof T]-?: {} extends Pick<T, K> ? never : K;
}[keyof T];

// Immutable builder: every set() returns a new builder whose type records the keys set so far (S).
class Builder<T, S extends Partial<T> = {}> {
  private constructor(private readonly state: S) {}

  static for<T>(): Builder<T, {}> {
    return new Builder<T, {}>({});
  }

  set<K extends keyof T>(key: K, value: T[K]): Builder<T, S & Pick<T, K>> {
    // A computed key widens the object type; the assertion restores the exact shape this line builds.
    const next = { ...this.state, [key]: value } as S & Pick<T, K>;
    return new Builder<T, S & Pick<T, K>>(next);
  }

  // Callable only when S holds every required key of T; otherwise `this` does not match and the call fails.
  build(this: Builder<T, S & Pick<T, RequiredKeys<T>>>): S & Pick<T, RequiredKeys<T>> {
    return { ...this.state };
  }
}

interface User {
  id: string;
  name: string;
  email: string;
  age?: number;
}

const user: User = Builder.for<User>()
  .set("id", "1")
  .set("name", "John")
  .set("email", "john@example.com")
  .build(); // OK: all required fields set

// @ts-expect-error missing required fields: name, email
Builder.for<User>().set("id", "1").build();

// @ts-expect-error age must be a number
Builder.for<User>().set("age", "40");

export { user };
```

### Pattern 4: Deep Readonly/Partial

```typescript
type DeepReadonly<T> = {
  readonly [P in keyof T]: T[P] extends object
    ? T[P] extends Function
      ? T[P]
      : DeepReadonly<T[P]>
    : T[P];
};

type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object
    ? T[P] extends Array<infer U>
      ? Array<DeepPartial<U>>
      : DeepPartial<T[P]>
    : T[P];
};

interface Config {
  server: {
    host: string;
    port: number;
    ssl: {
      enabled: boolean;
      cert: string;
    };
  };
  database: {
    url: string;
    pool: {
      min: number;
      max: number;
    };
  };
}

type ReadonlyConfig = DeepReadonly<Config>;
// All nested properties are readonly

type PartialConfig = DeepPartial<Config>;
// All nested properties are optional
```

### Pattern 5: Type-Safe Form Validation

```typescript
type ValidationRule<T> = {
  validate: (value: T) => boolean;
  message: string;
};

type FieldValidation<T> = {
  [K in keyof T]?: ValidationRule<T[K]>[];
};

type ValidationErrors<T> = {
  [K in keyof T]?: string[];
};

class FormValidator<T extends object> {
  constructor(private rules: FieldValidation<T>) {}

  validate(data: T): ValidationErrors<T> | null {
    const errors: ValidationErrors<T> = {};
    let hasErrors = false;

    for (const key in this.rules) {
      const fieldRules = this.rules[key];
      const value = data[key];

      if (fieldRules) {
        const fieldErrors: string[] = [];

        for (const rule of fieldRules) {
          if (!rule.validate(value)) {
            fieldErrors.push(rule.message);
          }
        }

        if (fieldErrors.length > 0) {
          errors[key] = fieldErrors;
          hasErrors = true;
        }
      }
    }

    return hasErrors ? errors : null;
  }
}

interface LoginForm {
  email: string;
  password: string;
}

const validator = new FormValidator<LoginForm>({
  email: [
    {
      validate: (v) => v.includes("@"),
      message: "Email must contain @"
    },
    {
      validate: (v) => v.length > 0,
      message: "Email is required"
    }
  ],
  password: [
    {
      validate: (v) => v.length >= 8,
      message: "Password must be at least 8 characters"
    }
  ]
});

const errors = validator.validate({
  email: "invalid",
  password: "short"
});
// Type: { email?: string[]; password?: string[]; } | null
```

### Pattern 6: Discriminated Unions

```typescript
type Success<T> = {
  status: "success";
  data: T;
};

type Failure = { // not `Error`: that name would shadow the global Error class
  status: "error";
  error: string;
};

type Loading = {
  status: "loading";
};

type AsyncState<T> = Success<T> | Failure | Loading;

function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}

function describeState<T>(state: AsyncState<T>, show: (data: T) => string): string {
  switch (state.status) {
    case "success":
      return show(state.data);  // Type: T
    case "error":
      return state.error;       // Type: string
    case "loading":
      return "Loading...";
    default:
      return assertNever(state); // a new variant without a case fails to compile
  }
}

// Type-safe state machine (data stays `unknown` until a schema parses it)
type State =
  | { type: "idle" }
  | { type: "fetching"; requestId: string }
  | { type: "success"; data: unknown }
  | { type: "error"; error: Error };

type Event =
  | { type: "FETCH"; requestId: string }
  | { type: "SUCCESS"; data: unknown }
  | { type: "ERROR"; error: Error }
  | { type: "RESET" };

function reducer(state: State, event: Event): State {
  switch (state.type) {
    case "idle":
      return event.type === "FETCH"
        ? { type: "fetching", requestId: event.requestId }
        : state;
    case "fetching":
      if (event.type === "SUCCESS") {
        return { type: "success", data: event.data };
      }
      if (event.type === "ERROR") {
        return { type: "error", error: event.error };
      }
      return state;
    case "success":
    case "error":
      return event.type === "RESET" ? { type: "idle" } : state;
  }
}
```

## Type Inference Techniques

### 1. Infer Keyword

```typescript
// Extract array element type
type ElementType<T> = T extends (infer U)[] ? U : never;

type NumArray = number[];
type Num = ElementType<NumArray>;  // number

// Extract promise type
type PromiseType<T> = T extends Promise<infer U> ? U : never;

type AsyncNum = PromiseType<Promise<number>>;  // number

// Extract function parameters
type Parameters<T> = T extends (...args: infer P) => any ? P : never;

function foo(a: string, b: number) {}
type FooParams = Parameters<typeof foo>;  // [string, number]
```

### 2. Type Guards

```typescript
function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isArrayOf<T>(
  value: unknown,
  guard: (item: unknown) => item is T
): value is T[] {
  return Array.isArray(value) && value.every(guard);
}

const data: unknown = ["a", "b", "c"];

if (isArrayOf(data, isString)) {
  data.forEach(s => s.toUpperCase());  // Type: string[]
}
```

### 3. Assertion Functions

```typescript
function assertIsString(value: unknown): asserts value is string {
  if (typeof value !== "string") {
    throw new Error("Not a string");
  }
}

function processValue(value: unknown) {
  assertIsString(value);
  // value is now typed as string
  console.log(value.toUpperCase());
}
```

## Best Practices

1. **Use `unknown` over `any`**: Enforce type checking
2. **Prefer `interface` for object shapes**: Better error messages
3. **Use `type` for unions and complex types**: More flexible
4. **Leverage type inference**: Let TypeScript infer when possible
5. **Create helper types**: Build reusable type utilities
6. **Use const assertions**: Preserve literal types
7. **Avoid type assertions**: Use type guards instead
8. **Document complex types**: Add JSDoc comments
9. **Use strict mode**: Enable all strict compiler options
10. **Test your types**: Use type tests to verify type behavior

## Type Testing

```typescript
// Type assertion tests: they run in `tsc`, so a wrong type fails the build.
type AssertEqual<T, U> =
  [T] extends [U]
    ? [U] extends [T]
      ? true
      : false
    : false;

type Expect<T extends true> = T;

type Test1 = Expect<AssertEqual<string, string>>;
type Test2 = Expect<AssertEqual<ReturnType<() => number>, number>>;

// A failing assertion is a compile error. An expect-error directive documents an expected failure
// and itself fails the build if the line below it ever starts compiling.
// @ts-expect-error string is not number
type Test3 = Expect<AssertEqual<string, number>>;
// @ts-expect-error a union is not equal to one of its members
type Test4 = Expect<AssertEqual<string | number, string>>;

export type { Test1, Test2, Test3, Test4 };
```

## Common Pitfalls

1. **Over-using `any`**: Defeats the purpose of TypeScript
2. **Ignoring strict null checks**: Can lead to runtime errors
3. **Too complex types**: Can slow down compilation
4. **Not using discriminated unions**: Misses type narrowing opportunities
5. **Forgetting readonly modifiers**: Allows unintended mutations
6. **Circular type references**: Can cause compiler errors
7. **Not handling edge cases**: Like empty arrays or null values

## Performance Considerations

- Avoid deeply nested conditional types
- Use simple types when possible
- Cache complex type computations
- Limit recursion depth in recursive types
- Use build tools to skip type checking in production

## Resources

- **TypeScript Handbook**: https://www.typescriptlang.org/docs/handbook/
- **Type Challenges**: https://github.com/type-challenges/type-challenges
- **TypeScript Deep Dive**: https://basarat.gitbook.io/typescript/
- **Effective TypeScript**: Book by Dan Vanderkam
