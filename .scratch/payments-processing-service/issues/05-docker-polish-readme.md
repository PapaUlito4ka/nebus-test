# 05 — Docker polish + README

**What to build:** A stack that starts cleanly from a cold checkout, and documentation that lets someone unfamiliar with the project run it and see every documented behaviour — happy path, idempotency conflict, and retry/DLQ — for themselves.

**Blocked by:** 03, 04

**Status:** ready-for-agent

- [ ] docker-compose healthchecks and `depends_on` ordering ensure `api`/`consumer` wait for `postgres`/`rabbitmq` readiness
- [ ] Alembic migrations run automatically on container startup
- [ ] `API_KEY` and other secrets are configured via environment variables in `docker-compose.yml`
- [ ] README documents: running `docker compose up`; example `curl` for `POST /api/v1/payments` and `GET /api/v1/payments/{id}`; an example of the idempotency-conflict (`409`) scenario; an example of triggering the retry/DLQ scenario (e.g. a `webhook_url` that always fails)
