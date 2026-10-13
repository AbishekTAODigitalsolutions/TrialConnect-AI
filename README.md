# Clinical Connect AI

Clinical Connect AI is a synthetic-data proof of concept for a clinical-trial patient engagement platform. It includes patient signup/login and coordinator patient management. No clinical AI, protocol logic, or medical advice is provided.

## Product summary

This POC includes:
- A FastAPI core service for health and readiness checks
- PostgreSQL 17 with the pgvector extension enabled
- Redis connectivity checks
- Synthetic patient seed data
- Patient signup and login, matching existing patient records by email
- Patient listing, search, and management in the coordinator workbench
- A combined patient chat that answers supported study FAQs and forwards unanswered questions to the coordinator
- Coordinator-scheduled appointments with in-portal reminders 48 and 24 hours before each visit
- Docker Compose orchestration for local development

## Safety boundary

This application is not a medical decision-making system. It does not diagnose conditions, prescribe medication, or generate clinical instructions from general LLM knowledge. Patient and staff authentication are local demonstrations only, email ownership is not verified, and the system lacks safeguards suitable for real patient records. Do not enter real patient information.

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
- Local Ollama model for the authenticated study information helper.

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

The project reads configuration from the ignored `.env` file. The included `.env.example` contains the required variables for API, database, Redis, and local Ollama integration. Never commit database credentials or other secrets.

Study FAQ answers use Ollama running locally, with no OpenAI account or internet search. On Windows with Docker Desktop, the API container reaches Ollama using `http://host.docker.internal:11434`. Configure `LLM_ENABLED=true`, `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://host.docker.internal:11434`, and `OLLAMA_MODEL` to a model installed in Ollama (the checked local model is `qwen3:4b`), then restart the API. Ensure Ollama is running and reachable from Docker. Ollama classifies unmatched questions into a fixed FAQ category; the app returns approved FAQ text for study questions. It can also give a short, general explanation of a medical term, followed by a clear notice that the response is not a diagnosis or recommendation. Questions about the user's symptoms, results, diagnosis, or treatment are redirected without being sent to the model. The assistant is not a medical or protocol decision system.

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

Set `COORDINATOR_ADMIN_EMAIL` and `COORDINATOR_ADMIN_PASSWORD` in `.env` to bootstrap the first admin account (password must be at least 12 characters). On first startup after the coordinator RBAC migration, the API creates this admin if no admin exists. It does not reset or replace an existing admin password on restart. Leave these values private; do not commit `.env`. If no admin is configured, staff login remains unavailable and the API logs a setup warning.

New coordinators can request access from the Coordinator Workbench sign-in page. The request is held pending until an admin approves it in **Settings → Coordinator access requests**; rejected applicants cannot sign in. The applicant's password is stored only as a hash and is not included in the admin email. To email the admin on new requests, configure the SMTP settings below (`SMTP_ENABLED=true`, host, port, sender, and optional credentials); if SMTP is unavailable, requests remain visible in the admin workbench and the UI reports that email was not sent. Admins can retry failed notifications.

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
- Patient authentication: `POST /api/v1/auth/signup`, `/login`, `GET /api/v1/auth/me`
- Coordinator authentication: `POST /api/v1/coordinator-auth/login`, `GET /api/v1/coordinator-auth/me`, `POST /api/v1/coordinator-auth/logout`
- Coordinator access requests: `POST /api/v1/coordinator-auth/access-requests`; admin review `GET /api/v1/coordinator-auth/access-requests`, `POST /api/v1/coordinator-auth/access-requests/{id}/decision`, and email retry `POST /api/v1/coordinator-auth/access-requests/{id}/notify`
- Admin staff management and audit: `GET/POST /api/v1/coordinator-auth/team`, `PATCH /api/v1/coordinator-auth/team/{id}`, `GET /api/v1/coordinator-auth/activity`
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
- [x] Tests pass without external AI credentials
- [x] POC uses synthetic data only
- [x] Clinical workflow, clinical AI, and medical advice remain out of scope

## Synthetic data notice

This POC uses synthetic patients and fictional study data only. No real patient data is included in the repository or the seeded data set.

## Phase 2 scope and limitations

- New patients create a portal account with a password of at least 12 characters; passwords are stored as scrypt hashes.
- Patients can create an account with their existing patient-record email and a password; no activation code or extra activation tab is needed. If the email has no matching patient record, the patient enters their name to create a new synthetic patient record.
- Patient login issues a signed, expiring bearer session; raw passwords are not stored in the database.
- Admin and coordinator staff can search patients and deactivate/reactivate records after signing in. Admins can create/disable coordinator accounts and review sign-in/message-read audit events.
- Deactivation is a soft state change; patient records are not hard-deleted.
- Email addresses are not verified, existing patient records can be claimed by signing up with their email, and this demo has no login rate limiting or recovery flow. Keep it local and synthetic-only; production use requires email verification and a security-reviewed identity and authorization system before any real patient data is used.
- Patient/coordinator messages are persisted in the configured database. Coordinator endpoints require a staff session; admin activity records successful/failed logins, sign-outs, and per-staff message reads. These audit records are for the local demo only and are not a substitute for a production audit system.
- Patient messages and the study assistant share one chat in the patient portal. Supported questions receive approved FAQ or brief general medical-term answers from the locally installed Ollama model when configured; questions the assistant cannot answer, personal symptom/result questions, and requests for diagnosis or treatment are forwarded to the study coordinator. The local model has no web-search access. Do not enter identifying or health information; the assistant is not a medical or protocol decision system.
- Patient and coordinator portals check for unread conversation messages every 15 seconds while open and refresh immediately when the tab becomes visible again. They show an unread count and an automatically updated Notifications page, and persist read status when the conversation is opened. Their left-side navigation also includes notification settings (in-app toast alerts can be disabled per browser) and About. These are in-app notifications only; there are no email, desktop, or browser push notifications for messages.
- Appointment scheduling creates a patient confirmation email and, when the appointment is more than 24 hours away, a reminder email scheduled for 24 hours before it. A durable outbox records each message's status, attempt count, last attempt, successful send time, and sanitized failure reason. The Celery worker checks the outbox once per minute, retries temporary delivery failures with backoff up to five attempts, and avoids duplicate outbox entries. The coordinator appointment panel shows the current delivery state. If SMTP is not configured, messages remain queued and the panel explicitly reports that SMTP configuration is needed.
- Configure SMTP in the ignored local `.env`: set `SMTP_ENABLED=true`, `SMTP_HOST`, `SMTP_PORT`, and `SMTP_FROM_EMAIL`; provide both `SMTP_USERNAME` and `SMTP_PASSWORD` when the server requires authentication, and leave both empty for unauthenticated SMTP. `SMTP_USE_STARTTLS=true` enables STARTTLS. Never commit real SMTP credentials. An appointment created less than 24 hours ahead receives a confirmation only because its 24-hour reminder time has already passed.
- Scheduling an appointment immediately creates an unread patient notification. The patient sees scheduled appointments and the 48-/24-hour reminder schedule in **Messages & AI**; due reminders appear in **Notifications** and can be marked read. The patient portal refreshes appointments and reminders every minute while open. Email is the only new outbound channel; there is no SMS or browser push delivery.
- Appointment date/time is entered using the coordinator browser’s local timezone, converted to UTC for storage, and displayed in the viewer’s browser timezone.
