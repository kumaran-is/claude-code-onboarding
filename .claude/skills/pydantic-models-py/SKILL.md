---
name: pydantic-models-py
description: Pydantic v2 multi-model pattern for clean API contracts — Base, Create, Update, Response variants with camelCase aliases and PATCH support. Use when defining FastAPI request/response schemas or data validation models.
allowed-tools: Read, Write, Edit
metadata:
  triggers: Pydantic models, API schema, request body, response model, Pydantic BaseModel, data validation, PATCH endpoint, camelCase alias, API contract, request/response schema
  related-skills: python-dev, openapi-spec-generation, api-design-principles
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-03-14"
---

## Iron Law

**NEVER USE A SINGLE PYDANTIC MODEL FOR BOTH CREATE AND RESPONSE — separate contracts prevent leaking internal fields, block over-posting, and make API evolution safe. Over-posting is only blocked when request models set `extra="forbid"`: Pydantic ignores unknown keys by default.**

# Pydantic v2 Models

Create Pydantic models following the multi-model pattern for clean, safe API contracts.

## Multi-Model Pattern

| Model | Purpose | Required Fields |
|-------|---------|-----------------|
| `Base` | Common fields shared across all variants | Shared, validated fields |
| `Create` | POST request body — fields the client supplies | Required fields only; `extra="forbid"` |
| `Update` | PATCH request body — partial update | All optional (use `None` default); `extra="forbid"` |
| `Response` | API response — all fields the client sees | Includes id, timestamps; lenient |
| `InDB` | Internal/repository layer — DO NOT expose directly | DB-only fields (e.g., hashed passwords) |

---

## Full Pattern Example

Executed on Pydantic 2.14 (`EmailStr` needs `pydantic[email]`).

```python
from datetime import datetime
from typing import ClassVar, Self
from uuid import UUID

from pydantic import (BaseModel, ConfigDict, EmailStr, Field, SecretStr,
                      model_validator)


class RequestModel(BaseModel):
    """Base for every request body: unknown keys are errors, not silently dropped."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ── Base: shared validated fields ──────────────────────────────────────────
class UserBase(RequestModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr                      # not a hand-written regex


# ── Create: POST /users body ────────────────────────────────────────────────
class UserCreate(UserBase):
    """Request body for user creation. Never include id, timestamps, role or owner ids."""
    password: SecretStr = Field(min_length=12, max_length=128)  # max_length bounds hashing cost; repr is masked


# ── Update: PATCH /users/{id} body ─────────────────────────────────────────
class UserUpdate(RequestModel):
    """Omit a field to leave it unchanged. Explicit null is rejected unless the column is nullable."""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    nickname: str | None = None          # the only nullable column: null means "clear it"

    NON_NULLABLE: ClassVar[frozenset[str]] = frozenset({"name", "email"})

    @model_validator(mode="after")
    def _no_null_for_non_nullable(self) -> Self:
        bad = sorted(f for f in self.model_fields_set & self.NON_NULLABLE if getattr(self, f) is None)
        if bad:
            raise ValueError(f"fields cannot be null: {bad}")
        return self


# ── Response: GET /users or POST /users response ────────────────────────────
class UserResponse(BaseModel):
    """What the API returns. Never include password or internal fields."""
    model_config = ConfigDict(from_attributes=True)  # ORM compatibility
    id: UUID
    name: str
    email: str
    created_at: datetime
    updated_at: datetime


# ── InDB: internal repository layer only ────────────────────────────────────
class UserInDB(UserResponse):
    """Internal model for repository layer. NEVER return this from a route."""
    hashed_password: str
```

Why `forbid` matters: without it, `{"nmae": "typo"}` validates to an empty model and a PATCH
becomes a no-op "success", and an injected `{"role": "admin"}` is silently dropped (executed).
With it both are 422 (`extra_forbidden`). Never put an actor id (`owner_id`, `author_id`, a role the
caller holds) in a request model: the actor comes from the verified token
(`python-dev/reference/fastapi-authorization-boundaries.md` §1).

---

## camelCase Aliases (for JS/TS clients)

```python
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class UserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        validate_by_name=True,    # accept snake_case on input...
        validate_by_alias=True,   # ...and camelCase
        serialize_by_alias=True,  # emit camelCase from model_dump() / FastAPI responses
    )
    workspace_id: str
    created_at: datetime
```

`validate_by_name` / `validate_by_alias` / `serialize_by_alias` need Pydantic 2.11+ (executed on 2.14);
they supersede `populate_by_name=True` (older flag; check the release notes of your pinned version
before removing it). With `serialize_by_alias=True` you no longer need `by_alias=True` on every dump.

---

## PATCH Endpoint — Partial Update Pattern

"Not sent" and "sent as null" are different. Decide per field and encode it in the Update model
(above): non-nullable fields reject explicit `null` (otherwise it reaches the ORM and fails with an
`IntegrityError` → 500), nullable fields accept it as "clear".

```python
async def update_project(id: UUID, payload: ProjectUpdate, session: AsyncSession) -> Project:
    project = await session.get(Project, id)
    if project is None:
        raise NotFoundError("Project", str(id))
    changes = payload.model_dump(exclude_unset=True)   # only what the client sent, nulls included
    for field, value in changes.items():               # safe: the model forbids unknown keys
        setattr(project, field, value)
    await session.commit()                             # the service owns the commit
    return project
```

Keep an allowlist of patchable fields on the model, never `setattr` from a free-form dict. Do not
document "None means do not change" together with `exclude_unset`: pick one meaning (executed:
`{}` → no changes, `{"nickname": null}` → clears it, `{"name": null}` → 422).

---

## Wire Types and Nullability

| Trap | Rule |
|------|------|
| `Decimal` serialises as a JSON **string** (`"12.50"`, OpenAPI `type: string`); `float`/`int` as numbers | Choose the wire type deliberately (integer minor units, or a documented string) — changing it breaks hand-written mobile/TS clients at runtime |
| Widening or removing a `WHERE` over a nullable column | Re-check every response field fed from it: non-Optional over nullable becomes `X \| None = None` in the same change; regenerate the OpenAPI snapshot |
| Password fields | `SecretStr` + `max_length`; never log `model_dump()` of a request containing them |
| Lists | Bound `max_length` on list fields and `page_size` on queries |

---

## PostgreSQL / SQLAlchemy Integration

```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

# ORM → Pydantic Response (from_attributes=True required)
user_response = UserResponse.model_validate(user_orm_instance)
```

ORM write traps in async code (executed on PostgreSQL):

| Trap | Fix |
|------|-----|
| A **server-side** `onupdate=func.now()` column is expired after the UPDATE; reading it raises `MissingGreenlet` even with `expire_on_commit=False` | `await session.refresh(obj, ["updated_at"])` (scoped), or use a Python-callable `onupdate` |
| A server-generated primary key is `None` until `flush()` (`str(row.id)` is `"None"`) | `await session.flush()` before reading it |
| Where the `flush()` sits decides where `IntegrityError` surfaces | Keep it inside the `try` that maps it to a domain error; re-point the race test if you move it |

Session and transaction ownership: `python-dev/reference/sqlalchemy-async-sessions-and-transactions.md`.

---

## Integration Steps

1. Create models in `src/<service>/schemas/<resource>.py`
2. Export from `src/<service>/schemas/__init__.py`
3. Import in routes: `from src.<service>.schemas.<resource> import UserCreate, UserResponse`
4. Use `Create` as request body param, `Response` as return type annotation
5. Use `model_validate(orm_obj)` in the service layer to convert ORM → Response
6. After any route/model change, regenerate the committed OpenAPI snapshot in the same PR (a stale snapshot compares stale to stale)

---

## Naming Conventions

| Model | Naming Pattern | Example |
|-------|---------------|---------|
| Base | `{Resource}Base` | `UserBase` |
| Create | `{Resource}Create` | `UserCreate` |
| Update | `{Resource}Update` | `UserUpdate` |
| Response | `{Resource}Response` | `UserResponse` |
| InDB | `{Resource}InDB` | `UserInDB` |

---

## Hard Prohibitions

- Never return `InDB` from a route handler — it contains internal fields (hashed passwords, etc.)
- Never leave a request model without `extra="forbid"`; never put an actor id or role in one
- Never use `Optional[str]` — use `str | None` (Python 3.10+ union syntax)
- Never use `@validator` — this is Pydantic v1 syntax; use `@field_validator` in v2
- Never use `orm_mode = True` — use `model_config = ConfigDict(from_attributes=True)` in v2
- Never use `.dict()` / `.json()` / `parse_obj` — use `model_dump()` / `model_dump_json()` / `model_validate()`
- Never apply a PATCH without `exclude_unset=True`; never accept explicit `null` for a non-nullable column
- Never hand-write an e-mail regex — use `EmailStr`; never store passwords in a plain `str` field that is logged
