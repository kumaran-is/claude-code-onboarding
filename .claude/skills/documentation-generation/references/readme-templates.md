# README Templates

Stack-specific README templates for projects in this workspace. Replace `${VARIABLE}` placeholders with actual values.

---

## Universal Template (all stacks)

```markdown
# ${PROJECT_NAME}

![Build](https://github.com/${GITHUB_ORG}/${REPO_NAME}/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-${LICENSE}-blue)

${SHORT_DESCRIPTION}

## Features

${FEATURES_LIST}

## Prerequisites

${PREREQUISITES}

## Quick Start

```bash
${QUICK_START_COMMANDS}
```

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| ${VAR_1} | ${DESCRIPTION_1} | — | Yes |
| ${VAR_2} | ${DESCRIPTION_2} | — | No |

Copy `.env.example` to `.env` and fill in the required values.

## Development

```bash
${DEV_COMMANDS}
```

## Testing

```bash
${TEST_COMMANDS}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit using conventional commits (`git commit -m 'feat: add feature'`)
4. Push and open a Pull Request

## License

This project is licensed under the ${LICENSE} License.
```

---

## Java / Spring Boot variant

```markdown
# ${SERVICE_NAME} — Spring Boot Service

Java 25, Spring Boot 4.2 (MVC default, WebFlux when justified), PostgreSQL

## Prerequisites

- JDK 25
- Maven 3.10.2
- PostgreSQL 15+
- Docker (optional, for local deps)

## Quick Start

```bash
# Start dependencies
docker-compose up -d postgres

# Run in dev mode
./mvnw spring-boot:run -Dspring-boot.run.profiles=local

# Build JAR
./mvnw clean package -DskipTests
```

## Configuration

```properties
# application.properties
spring.datasource.url=jdbc:postgresql://localhost:5432/${DB_NAME}
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
```

## Testing

```bash
./mvnw test                  # unit tests
./mvnw verify                # unit + integration tests
./mvnw test -Dtest=*IT       # integration tests only
```
```

---

## NestJS variant

```markdown
# ${SERVICE_NAME} — NestJS Service

Node.js 24.14.x, NestJS 11.2.x, Fastify, Prisma 7, TypeScript 5.9.x

## Prerequisites

- Node.js 24+
- npm 10+
- PostgreSQL 15+

## Quick Start

```bash
npm install
cp .env.example .env         # fill in DATABASE_URL and other secrets
npx prisma migrate deploy    # apply migrations
npm run start:dev            # start with hot reload
```

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `JWT_SECRET` | JWT signing secret (min 32 chars) | Yes |
| `PORT` | Server port (default: 3000) | No |

## Testing

```bash
npm test                     # unit tests
npm run test:e2e             # end-to-end tests
npm run test:cov             # coverage report
```
```

---

## Python / FastAPI variant

```markdown
# ${SERVICE_NAME} — FastAPI Service

Python 3.14, FastAPI 0.165.0, Pydantic v2, SQLAlchemy async

## Prerequisites

- Python 3.14+
- uv (recommended) or pip

## Quick Start

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API docs available at: `http://localhost:8000/docs`

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | Async PostgreSQL URL | Yes |
| `SECRET_KEY` | App secret (min 32 chars) | Yes |
| `ENVIRONMENT` | dev / staging / prod | No |

## Testing

```bash
pytest                       # all tests
pytest --cov=app             # with coverage
pytest -m integration        # integration only
```
```

---

## Flutter variant

```markdown
# ${APP_NAME} — Flutter App

Flutter 3.50.x, Dart 3.14.0, cross-platform (iOS + Android)

## Prerequisites

- Flutter 3.50.x+
- Dart 3.14.0+
- Xcode 16+ (iOS)
- Android Studio (Android)

## Quick Start

```bash
flutter pub get
flutter run                  # default device
flutter run -d ios           # iOS simulator
flutter run -d android       # Android emulator
```

## Configuration

Copy `lib/config/env.example.dart` to `lib/config/env.dart` and fill in:
- Firebase project config
- API base URL

## Testing

```bash
flutter test                 # unit + widget tests
flutter test integration_test/ -d <device-id>  # in-process integration tests (needs a device/simulator)
maestro test .maestro/          # Android/iOS UI/E2E flows (Maestro only)
```
```

---

## Badge patterns

```markdown
![Build](https://github.com/ORG/REPO/actions/workflows/ci.yml/badge.svg)
![Coverage](https://codecov.io/gh/ORG/REPO/branch/main/graph/badge.svg)
![Version](https://img.shields.io/github/package-json/v/ORG/REPO)
![License](https://img.shields.io/badge/license-MIT-blue)
![Java](https://img.shields.io/badge/java-25-orange)
![Spring Boot](https://img.shields.io/badge/spring--boot-4.2-green)
![Flutter](https://img.shields.io/badge/flutter-3.50.x-blue)
```
