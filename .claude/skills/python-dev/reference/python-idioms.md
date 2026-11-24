# Python Idioms Reference

Python 3.14 (validated on 3.14.10): this workspace's stack version. Section 9 lists the 3.14 language changes that alter everyday code.

---

## Section 1 — EAFP over LBYL

**LBYL (Look Before You Leap)** — the anti-pattern:
```python
# Avoid: pre-check before access
if 'key' in data:
    value = data['key']
else:
    value = default

# Avoid: TOCTOU race condition with files
if os.path.exists(path):
    with open(path) as f:  # file could disappear between check and open
        content = f.read()
```

**EAFP (Easier to Ask Forgiveness than Permission)** — the Python idiom:
```python
# Correct: try and handle
try:
    value = data['key']
except KeyError:
    value = default

# Even better for dicts:
value = data.get('key', default)

# Correct: EAFP with files
try:
    with open(path) as f:
        content = f.read()
except FileNotFoundError:
    content = None
```

**Rule:** Use EAFP for dict access, attribute access, file I/O, and type coercion. LBYL
introduces TOCTOU race conditions (check-then-act on external state) and redundant lookups.

---

## Section 2 — Protocol-based duck typing

Use `Protocol` instead of ABC when the interface is structural, not behavioral inheritance.

```python
from dataclasses import dataclass
from typing import Protocol, Self, runtime_checkable


# Structural interface: no inheritance required
@runtime_checkable
class Serializable(Protocol):
    def to_dict(self) -> dict[str, object]: ...

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self: ...


# Any class with these methods satisfies the Protocol; it never imports Serializable
@dataclass(frozen=True, slots=True)
class UserRecord:
    id: int
    name: str

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self:
        return cls(id=int(str(data["id"])), name=str(data["name"]))


def save(obj: Serializable) -> None:
    payload = obj.to_dict()  # mypy checks the structural match
    ...


# runtime_checkable allows isinstance (it checks method presence only, not signatures)
assert isinstance(UserRecord(1, "a"), Serializable)
```

Executed on 3.14.10 (`mypy --strict` and ruff clean). `Self` replaces the quoted `'Serializable'` / `'UserModel'` return types.

**Rule:** Use `Protocol` when callers should not be forced to import and subclass your ABC.
Use ABC when shared implementation (mixin methods) is genuinely needed.

---

## Section 3 — Exception chaining (preserve traceback)

```python
# Anti-pattern: hides original exception and traceback
try:
    result = db.query(sql)
except DatabaseError as e:
    raise AppError("Query failed")  # original traceback LOST

# Correct: preserve original exception
try:
    result = db.query(sql)
except DatabaseError as e:
    raise AppError("Query failed") from e  # chains, preserves traceback

# Explicit suppression (intentional):
try:
    value = cache.get(key)
except CacheError:
    raise CacheMissError(key) from None  # from None = intentional, document why
```

**Rule:** Always use `raise X from e` when re-raising inside an except block. Use `from None`
only when the original error is intentionally suppressed — leave a comment explaining why.

Note: This skill's FastAPI error handling templates (`fastapi-error-handling.md:174,286`)
already use `from exc` consistently. This section is the general rule behind that pattern.

---

## Section 4 — Mutable default argument anti-pattern

```python
# BUG: list/dict default args are shared across ALL calls
def add_item(item: str, items: list[str] = []) -> list[str]:
    items.append(item)  # mutates the shared default!
    return items

add_item('a')  # ['a']
add_item('b')  # ['a', 'b'] — wrong! should be ['b']

# Correct: use None sentinel
def add_item(item: str, items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    items.append(item)
    return items

# Same rule for dataclass fields — use field(default_factory=...):
from dataclasses import dataclass, field

@dataclass
class Config:
    tags: list[str] = field(default_factory=list)   # correct
    meta: dict[str, str] = field(default_factory=dict)  # correct
    # tags: list[str] = []  ← WRONG — shared across all Config instances
```

**Rule:** NEVER use mutable objects (`list`, `dict`, `set`) as default argument values.
Use `None` as sentinel for functions; use `field(default_factory=...)` for dataclasses.

---

## Section 5 — `__slots__` (memory-critical classes)

Already covered in `python-advanced-patterns.md` (lines 320–360) with full trade-off analysis.

**Summary rule:** Use `__slots__ = ('x', 'y')` when creating thousands of instances.
Eliminates per-instance `__dict__`, reducing memory ~40–60%. Do NOT use for Pydantic models,
SQLAlchemy ORM models, or general application models.

---

## Section 6 — `isinstance()` vs `type()` equality

```python
# Anti-pattern: type() equality breaks inheritance
def process(obj):
    if type(obj) == int:  # fails for bool (bool is subclass of int)
        ...

# Correct: isinstance() respects inheritance
def process(obj):
    if isinstance(obj, int):  # True for int AND bool
        ...

# isinstance with tuple for multiple types:
if isinstance(value, (int, float)):
    ...

# type() equality is ONLY correct when you explicitly EXCLUDE subclasses:
if type(obj) is int:  # use 'is', not '==' for type comparison
    ...  # intentionally excludes bool — add a comment when you do this
```

**Rule:** Always use `isinstance()` for type checks. Use `type(x) is T` only when you
intentionally need to exclude subclasses, and always document why.

---

## Section 7 — `is None` vs `== None`

```python
# Anti-pattern: == None uses __eq__ which can be overridden by custom classes
if value == None:   # could return True for objects overriding __eq__
    ...

# Correct: is None is an identity check (None is a singleton)
if value is None:
    ...

if value is not None:
    ...

# Same rule for True/False identity checks (when you need strict bool, not truthy):
if flag is True:    # only matches True, not other truthy values
    ...
if flag is False:   # only matches False, not other falsy values
    ...

# For truthiness checks (most common case), plain if/not is correct:
if value:           # truthy check — preferred over == True
    ...
if not value:       # falsy check — preferred over == False
    ...
```

**Rule:** Use `is None` / `is not None` for None checks. Use `== None` nowhere.
Use bare `if value:` for truthiness; use `is True` / `is False` only when strict
bool identity matters (e.g., tristate logic with None/True/False).

---

## Section 8 — Dataclass `__post_init__` for validation

```python
from dataclasses import dataclass, field

@dataclass
class Config:
    host: str
    port: int
    timeout_seconds: float = 30.0
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Validation runs after the generated __init__ completes
        if not self.host:
            raise ValueError("host cannot be empty")
        if not (1 <= self.port <= 65535):
            raise ValueError(f"Invalid port: {self.port}")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        # Normalize
        self.host = self.host.lower().strip()

# Usage — validation fires automatically:
Config(host='  DB.EXAMPLE.COM  ', port=5432)  # normalized to 'db.example.com'
Config(host='', port=5432)  # raises ValueError immediately
```

**Rule:** Use `__post_init__` for all dataclass validation and normalization. Do NOT add
separate `validate()` methods that callers must remember to call — that is an untested
invariant waiting to be violated.

For API-layer models, prefer Pydantic v2 (`@field_validator`, `model_validator`) — see
`fastapi-templates.md`. Use dataclass `__post_init__` for domain/internal value objects
that must not depend on Pydantic.

---

## Section 9 — Python 3.14 language changes that alter everyday code

Source: "What's New In Python 3.14" (docs.python.org). Every row executed on CPython 3.14.10 (uv-managed) unless marked "docs"; the same files fail on 3.13 where noted.

| Change | Do in new 3.14-only code | Evidence |
|---|---|---|
| Deferred evaluation of annotations (PEP 649/749) | Drop `from __future__ import annotations` and quoted forward references; `parent: Category \| None` and a reference to a class defined later in the module just work. The `__future__` import still works but is deprecated (removal not before 3.13 EOL, docs) | Pydantic 2.14.4 model with a self reference and a later-defined class, served by FastAPI 0.165.0: valid body 200, invalid 422, OpenAPI generated. Same file on 3.13: `NameError: name 'Category' is not defined` |
| `annotationlib` | Read annotations at runtime with `annotationlib.get_annotations(obj, format=Format.FORWARDREF)` (or `Format.STRING`) when names may be undefined; `Format.VALUE` (the default) raises `NameError` for them. Do not read `__annotations__` directly in framework-style code | executed |
| Template strings, `t"..."` (PEP 750) | A t-string is a `string.templatelib.Template` (static parts plus `Interpolation` objects), not a `str`: use it to build library APIs that escape values (HTML, shell, logging). For SQL keep SQLAlchemy bind parameters; never hand-roll SQL from a t-string in application code | a 10-line renderer turned `t"... WHERE name = {user}"` into `"... = %s"` plus `[user]`; mypy 2.4.1 and ruff 0.17.6 accept the syntax |
| `except A, B:` without brackets (PEP 758, only without `as`) | Allowed; with `target-version = "py314"` ruff 0.17.6 `format` REWRITES `except (A, B):` to `except A, B:`, which is a `SyntaxError` on 3.13. Set ruff's `target-version` from `requires-python`, never higher | executed: ruff diff shown, 3.13 import fails |
| `return` / `break` / `continue` in `finally` (PEP 765) | Now a `SyntaxWarning` (an error under `-W error`): it silently swallowed in-flight exceptions; move the statement out of `finally` | executed |
| Concurrent safe warnings, `-X context_aware_warnings` | `warnings.catch_warnings` is context-local by default only on the free-threaded build (docs); tests that assert warnings from threads should not rely on the GIL build default | docs |

Asyncio changes (loop factory, `get_event_loop()` now raising, call-graph introspection, `forkserver` default): `asyncio-concurrency-and-tasks.md` sections 5–5b. Runtime/packaging choices (3.14 vs 3.15, free-threaded build, subinterpreters): `.claude/skills/python-patterns/SKILL.md`.
