# 01 — Project skeleton: docker-compose + migrations + health check

**What to build:** The runnable foundation the rest of the service builds on — a `docker compose up` that brings up all four services from the spec, database tables for `payments` and `outbox`, and an unauthenticated health check other services can depend on.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] `docker compose up` starts `postgres`, `rabbitmq` (`rabbitmq:management` image, no external plugins), `api`, `consumer`
- [ ] Alembic migration creates `payments` table: `id` (UUID4 PK), `amount` (Decimal, 2 decimal places), `currency` (enum `RUB`/`USD`/`EUR`), `description` (nullable), `metadata` (JSONB, default `{}`), `status` (enum `pending`/`succeeded`/`failed`, default `pending`), `idempotency_key` (unique, not null), `webhook_url` (not null), `created_at`, `processed_at` (nullable)
- [ ] Alembic migration creates `outbox` table: `id`, `payload` (JSONB), `created_at`, `published_at` (nullable)
- [ ] `GET /health` returns `200` without requiring `X-API-Key`
