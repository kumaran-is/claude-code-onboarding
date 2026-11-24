# Implementation Patterns

> Code-level patterns for Clean Architecture and Hexagonal Architecture.
> Part of the `architecture-design` skill.
> For DDD patterns (Aggregates, Value Objects, Bounded Contexts) use the `ddd-architect` skill.

## Clean Architecture (Uncle Bob)

### Concept

Layers with inward dependency flow — inner layers know nothing about outer layers:

```
+---------------------------+
|   Frameworks & Drivers    |  (FastAPI, Prisma, Stripe SDK)
|  +-----------------------+|
|  | Interface Adapters    ||  (Controllers, Repositories, Gateways)
|  |  +-------------------+|
|  |  |   Use Cases       ||  (Application business rules)
|  |  |  +---------------+|
|  |  |  |   Entities    ||  (Core business models)
|  |  |  +---------------+|
|  |  +-------------------+|
|  +-----------------------+|
+---------------------------+

Dependency rule: arrows always point INWARD.
Entities do not import Use Cases. Use Cases do not import Controllers.
```

### Key Principles

- Dependencies point inward only
- Inner layers know nothing about outer layers
- Business logic is independent of frameworks
- Core is testable without UI, database, or external services

### Directory Structure

```
app/
+-- domain/           # Entities and business rules (no imports from outer layers)
|   +-- entities/
|   |   +-- user.py
|   |   +-- order.py
|   +-- value_objects/
|   |   +-- email.py
|   |   +-- money.py
|   +-- interfaces/   # Abstract interfaces (ports defined here, implemented outside)
|       +-- user_repository.py
|       +-- payment_gateway.py
+-- use_cases/        # Application business rules (orchestrates entities via interfaces)
|   +-- create_user.py
|   +-- process_order.py
+-- adapters/         # Interface implementations (repositories, controllers, gateways)
|   +-- repositories/
|   |   +-- postgres_user_repository.py
|   |   +-- redis_cache_repository.py
|   +-- controllers/
|   |   +-- user_controller.py
|   +-- gateways/
|       +-- stripe_payment_gateway.py
+-- infrastructure/   # Framework and external concerns
    +-- database.py
    +-- config.py
    +-- logging.py
```

### Python / FastAPI Example

```python
# domain/entities/user.py
# NO framework imports — pure Python dataclass
from dataclasses import dataclass
from datetime import datetime

@dataclass
class User:
    id: str
    email: str
    name: str
    created_at: datetime
    is_active: bool = True

    def deactivate(self):
        self.is_active = False

    def can_place_order(self) -> bool:
        return self.is_active


# domain/interfaces/user_repository.py
# Port: defines contract, no implementation
from abc import ABC, abstractmethod
from typing import Optional
from domain.entities.user import User

class IUserRepository(ABC):
    @abstractmethod
    async def find_by_id(self, user_id: str) -> Optional[User]:
        pass

    @abstractmethod
    async def find_by_email(self, email: str) -> Optional[User]:
        pass

    @abstractmethod
    async def save(self, user: User) -> User:
        pass


# use_cases/create_user.py
# Orchestrates business logic — depends only on domain interfaces
from domain.entities.user import User
from domain.interfaces.user_repository import IUserRepository
from dataclasses import dataclass
from datetime import datetime
import uuid

@dataclass
class CreateUserRequest:
    email: str
    name: str

class CreateUserUseCase:
    def __init__(self, user_repository: IUserRepository):
        self.user_repository = user_repository

    async def execute(self, request: CreateUserRequest) -> User:
        existing = await self.user_repository.find_by_email(request.email)
        if existing:
            raise ValueError("Email already exists")

        user = User(
            id=str(uuid.uuid4()),
            email=request.email,
            name=request.name,
            created_at=datetime.now(),
        )
        return await self.user_repository.save(user)


# adapters/repositories/postgres_user_repository.py
# Adapter: PostgreSQL implementation of the domain interface
from domain.interfaces.user_repository import IUserRepository
from domain.entities.user import User
from typing import Optional
import asyncpg

class PostgresUserRepository(IUserRepository):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def find_by_id(self, user_id: str) -> Optional[User]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            return self._to_entity(row) if row else None

    async def find_by_email(self, email: str) -> Optional[User]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
            return self._to_entity(row) if row else None

    async def save(self, user: User) -> User:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (id, email, name, created_at, is_active)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE
                SET email = $2, name = $3, is_active = $5
                """,
                user.id, user.email, user.name, user.created_at, user.is_active
            )
            return user

    def _to_entity(self, row) -> User:
        return User(
            id=row["id"], email=row["email"], name=row["name"],
            created_at=row["created_at"], is_active=row["is_active"]
        )


# adapters/controllers/user_controller.py
# Controller: handles HTTP concerns ONLY — delegates to use case
from fastapi import APIRouter, Depends, HTTPException
from use_cases.create_user import CreateUserUseCase, CreateUserRequest
from pydantic import BaseModel

router = APIRouter()

class CreateUserDTO(BaseModel):
    email: str
    name: str

@router.post("/users", status_code=201)
async def create_user(dto: CreateUserDTO, use_case: CreateUserUseCase = Depends()):
    try:
        user = await use_case.execute(CreateUserRequest(email=dto.email, name=dto.name))
        return {"id": user.id, "email": user.email, "name": user.name}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
```

---

## Hexagonal Architecture (Ports and Adapters)

### Concept

The application core (domain) is surrounded by ports (interfaces) and adapters (implementations):

```
           [REST Controller]   [CLI Adapter]
                  |                 |
           +------+-----------------+------+
           |           PORTS               |
           |  [OrderRepositoryPort]        |
           |  [PaymentGatewayPort]         |   <- Primary ports (driven by outside)
           |  [NotificationPort]           |
           |  +---------------------------+|
           |  |     DOMAIN CORE           ||
           |  |   (OrderService)          ||
           |  +---------------------------+|
           |                               |
           +------+-------------------+----+
                  |                   |
        [PostgresAdapter]   [StripeAdapter]  [MockPaymentAdapter]
                                             (for testing)
```

### Key Benefits

- Swap implementations without changing business logic (e.g., Stripe -> PayPal)
- Mock adapters for testing without running external services
- Technology-agnostic domain core

### Python / FastAPI Example

```python
# Ports (interfaces) — defined in domain layer
from abc import ABC, abstractmethod

class OrderRepositoryPort(ABC):
    @abstractmethod
    async def save(self, order: Order) -> Order:
        pass

class PaymentGatewayPort(ABC):
    @abstractmethod
    async def charge(self, amount: float, customer_id: str) -> PaymentResult:
        pass

class NotificationPort(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, body: str) -> None:
        pass


# Domain core (hexagon center) — depends only on ports, not implementations
class OrderService:
    def __init__(
        self,
        order_repository: OrderRepositoryPort,
        payment_gateway: PaymentGatewayPort,
        notification_service: NotificationPort
    ):
        self.orders = order_repository
        self.payments = payment_gateway
        self.notifications = notification_service

    async def place_order(self, order: Order) -> OrderResult:
        if not order.is_valid():
            return OrderResult(success=False, error="Invalid order")

        payment = await self.payments.charge(
            amount=order.total, customer_id=order.customer_id
        )
        if not payment.success:
            return OrderResult(success=False, error="Payment failed")

        order.mark_as_paid()
        saved_order = await self.orders.save(order)

        await self.notifications.send(
            to=order.customer_email,
            subject="Order confirmed",
            body=f"Order {order.id} confirmed"
        )
        return OrderResult(success=True, order=saved_order)


# Primary adapter: Stripe (production)
class StripePaymentAdapter(PaymentGatewayPort):
    def __init__(self, api_key: str):
        import stripe
        stripe.api_key = api_key
        self.stripe = stripe

    async def charge(self, amount: float, customer_id: str) -> PaymentResult:
        try:
            charge = self.stripe.Charge.create(
                amount=int(amount * 100),  # cents
                currency="usd",
                customer=customer_id
            )
            return PaymentResult(success=True, transaction_id=charge.id)
        except self.stripe.CardError as e:  # top-level in stripe 17; stripe.error is only an alias
            return PaymentResult(success=False, error=e.code)  # provider code, not provider message


# Test adapter: Mock (no external dependencies — use in unit tests)
class MockPaymentAdapter(PaymentGatewayPort):
    async def charge(self, amount: float, customer_id: str) -> PaymentResult:
        return PaymentResult(success=True, transaction_id="mock-txn-123")
```

---

## Pattern Applicability by Stack

| Pattern | NestJS (TypeScript) | Spring Boot (Java) | Python FastAPI |
|---------|--------------------|--------------------|----------------|
| Clean Architecture | Yes - Modules as layers | Yes - Native (packages) | Yes - Directories as layers |
| Hexagonal | Yes - Interfaces as ports | Yes - Interfaces as ports | Yes - ABC as ports |
| Repository | Yes - Prisma with interface | Yes - Spring Data R2DBC | Yes - SQLAlchemy async |
| Use Cases | Yes - Service classes | Yes - @Service classes | Yes - Service classes |
| DDD Aggregates | See `ddd-architect` | See `ddd-architect` | See `ddd-architect` |

## Common Pitfalls

| Pitfall | What It Looks Like | Fix |
|---------|-------------------|-----|
| **Anemic Domain** | Entity has only fields, all logic in services | Move business methods into entity |
| **Framework Coupling** | Business logic imports FastAPI/NestJS | Move to use case layer — no framework imports |
| **Fat Controllers** | Controller contains business logic | Delegate to use case immediately |
| **Repository Leakage** | ORM model (Prisma/SQLAlchemy) returned to caller | Map to domain entity at repository boundary |
| **Over-Engineering** | Clean Architecture for simple CRUD | Direct ORM in service for simple cases |

## Best Practices

1. **Dependency Rule**: Dependencies always point inward — never outward
2. **Interface Segregation**: Small, focused interfaces — not one god interface
3. **Business Logic in Domain**: Keep framework imports out of entities and use cases
4. **Test Independence**: Core must be testable without running a database or HTTP server
5. **Thin Controllers**: Controllers only handle HTTP/serialization — all logic in use cases
6. **Rich Domain Models**: Entities carry behavior, not just data
