# Clinical Connect AI

Clinical Connect AI is a synthetic-data proof of concept for a clinical-trial patient engagement platform. It includes patient signup/login, activation of existing patient records, and coordinator patient management. No clinical AI, protocol logic, or medical advice is provided.

## Product summary

This POC includes:
- A FastAPI core service for health and readiness checks
- PostgreSQL 17 with the pgvector extension enabled
- Redis connectivity checks
- Synthetic patient seed data
- Patient signup, login, and one-time activation codes for existing patient records
- Patient listing, search, and activation management in the coordinator workbench
- Logged-in patient-to-coordinator messages and a bounded study FAQ helper
- Coordinator-scheduled appointments with in-portal reminders 48 and 24 hours before each visit
- Docker Compose orchestration for local development

## Safety boundary

This application is not a medical decision-making system. It does not diagnose conditions, prescribe medication, or generate clinical instructions from general LLM knowledge. Patient authentication is a local demonstration only; coordinator endpoints are not authenticated, email ownership is not verified, and the system lacks safeguards suitable for real patient records. Do not enter real patient information.

## Technology stack

- Python 3.12
- FastAPI
- SQLAlchemy 2.x
- Alembic
- PostgreSQL 17 + pgvector
- Redis
- Celery
- React + TypeScript + Vite
- Tailwind CSS
- Docker Compose
- OpenAI Responses API with web search for the authenticated study information helper (requires explicit local configuration).

## Prerequisites

- Docker Desktop or Docker Engine
- Docker Compose v2
- Python 3.12 (optional for local development outside Docker)
- Node.js 20+ (optional for local frontend development outside Docker)

## Local setup

1. Copy the example environment file:
   ```powershell
   copy .env.example .env
   ```
2. Build and start the stack:
   ```powershell
   docker compose up --build -d
   ```
3. Verify the containers:
   ```powershell
   docker compose ps
   ```

## Environment configuration

The project reads configuration from the ignored `.env` file. The included `.env.example` contains the required variables for API, database, Redis, and optional OpenAI integration. Never commit database credentials, API keys, or other secrets.

To enable OpenAI-backed study answers, set `LLM_ENABLED=true`, `LLM_PROVIDER=openai`, `OPENAI_API_KEY` to your secret API key, and `OPENAI_MODEL` to a model available to your account that supports the Responses API web-search tool. Restart the API after changing these settings. Without these values, the helper uses its fixed FAQ answers.

### Use an existing local PostgreSQL server

To connect the Dockerized API to a PostgreSQL server running on the Windows host, set these values in `.env`:

```dotenv
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5433
POSTGRES_DB=mydb
POSTGRES_USER=taopostgres
POSTGRES_PASSWORD=<set locally; do not commit>
POSTGRES_SCHEMA=trialconnect
REQUIRE_PGVECTOR=false
```

Use `127.0.0.1` as the host instead when running the API directly on Windows rather than in Docker. The migration creates the configured schema if it does not exist and keeps TrialConnect tables there; it does not modify tables in `public`. The PostgreSQL role must be allowed to connect to `mydb` and create objects in the configured schema. Set `REQUIRE_PGVECTOR=true` only when the server has pgvector installed in that database.

Set `AUTH_SECRET` to a private random value of at least 32 bytes before starting the stack. Keep it only in `.env`; replacing it invalidates existing patient sessions.

## Docker commands

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f trialconnect-core
docker compose down
```

## Migration commands

```powershell
docker compose exec trialconnect-core alembic upgrade head
```

## Seed commands

```powershell
docker compose exec trialconnect-core python -m app.database.seed
```

## Test commands

```powershell
docker compose exec trialconnect-core pytest
```

## Portal URLs

- Patient portal: http://localhost:3000
- Coordinator workbench: http://localhost:3001
- Core API: http://localhost:8000
- OpenAPI docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Readiness: http://localhost:8000/api/v1/readiness
- PostgreSQL host port: 5434
- Patient API: `GET /api/v1/patients`, `GET/PATCH/DELETE /api/v1/patients/{id}`
- Patient authentication: `POST /api/v1/auth/signup`, `/login`, `/activate`, `GET /api/v1/auth/me`
- Coordinator-issued activation code: `POST /api/v1/auth/patients/{id}/invite`
- Patient conversation: authenticated `GET/POST /api/v1/messages`
- Coordinator conversation: `GET/POST /api/v1/coordinator/patients/{id}/messages`
- Bounded study FAQ: authenticated `POST /api/v1/assistant/faq`
- Coordinator schedules: `GET/POST /api/v1/coordinator/patients/{id}/appointments`
- Patient appointments and reminders: authenticated `GET /api/v1/appointments`, `GET /api/v1/notifications`, `PATCH /api/v1/notifications/{id}/read`

## Troubleshooting

- If the database container is unhealthy, check `docker compose logs clinical-data-store`.
- If the API reports failed readiness, confirm PostgreSQL and Redis are healthy before retrying.
- Rebuild services after dependency changes using `docker compose up --build -d`.
- Confirm no Azure credentials are required for Phase 1 tests.

## Foundation checklist

- [x] Docker Compose local stack boots
- [x] PostgreSQL health checks pass
- [x] pgvector extension available
- [x] Redis health checks pass
- [x] FastAPI health endpoint responds successfully
- [x] Readiness endpoint checks PostgreSQL, pgvector, and Redis
- [x] Alembic migrations succeed
- [x] Seed command is idempotent
- [x] Exactly 20 synthetic patient records are seeded
- [x] Correlation IDs are returned in API responses
- [x] Tests pass without OpenAI credentials
- [x] POC uses synthetic data only
- [x] Clinical workflow, clinical AI, and medical advice remain out of scope

## Synthetic data notice

This POC uses synthetic patients and fictional study data only. No real patient data is included in the repository or the seeded data set.

## Phase 2 scope and limitations

- New patients create a portal account with a password of at least 12 characters; passwords are stored as scrypt hashes.
- Existing patient records receive a one-time activation code from the coordinator and set a password when activating.
- Patient login issues a signed, expiring bearer session; raw passwords and activation codes are not stored in the database.
- Coordinators can search patients, create activation codes, and deactivate/reactivate records.
- Activation codes expire after 72 hours and are single-use; creating a new code invalidates prior unused codes.
- Deactivation is a soft state change; patient records are not hard-deleted.
- Email addresses are not verified, coordinator routes are not authenticated, and this demo has no login rate limiting or recovery flow. Keep it local and synthetic-only; production use requires a security-reviewed identity and authorization system before any real patient data is used.
- Patient/coordinator messages are persisted in the configured database. Coordinator messaging is unauthenticated in this local demo, so it must not be exposed beyond loopback or used for real patient information.
- The AI web search helper uses OpenAI Responses API web search for non-medical questions when `LLM_ENABLED=true`, `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_MODEL` are configured in the ignored local `.env`. Study-specific facts are limited to approved study information. Medical questions are redirected without sending them to OpenAI. OpenAI receives the submitted question, so do not enter identifying or health information. Web citations are returned for display; the assistant is not a medical or protocol decision system.
- Conversation does not provide live chat or push notifications. Patients/coordinators refresh or reopen the conversation to see new messages.
- Appointment reminders are in-app only. The Celery worker/beat checks once per minute and writes each 48-hour and 24-hour reminder at most once; the patient portal refreshes notifications every minute while open. There is no email, SMS, or browser push delivery.
- Appointment date/time is entered using the coordinator browser’s local timezone, converted to UTC for storage, and displayed in the viewer’s browser timezone.
