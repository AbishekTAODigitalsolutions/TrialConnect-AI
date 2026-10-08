# Phase 1 notes

The foundation includes service health, PostgreSQL/pgvector, Redis, migrations, audit events, and synthetic patient records. The patient portal provides demo signup/login, existing records can be activated through a one-time coordinator-issued code, and logged-in patients can message a coordinator, ask the limited study FAQ helper, and receive in-app appointment reminders 48 and 24 hours before a coordinator-scheduled appointment.

The application still stops before clinical advice, protocol decisions, or escalation logic. The FAQ helper is deterministic and uses fixed answers, not an LLM. Reminders are in-app only and depend on the periodic worker. Demo patient authentication does not verify email addresses; coordinator endpoints remain unauthenticated. Keep it local and synthetic-only; these controls are not suitable for real patient records.
