# 02 — Happy-path payment pipeline end-to-end

**What to build:** The full payment pipeline working end-to-end for the happy path — a caller can create a payment, it moves through Outbox → RabbitMQ → Consumer → Gateway emulation, and the caller can observe the result both via `GET` and via a webhook, with correlated structured logs across every stage. Retry/DLQ behaviour and idempotency-key conflict handling are deliberately out of scope here — this ticket proves the pipeline works when nothing fails.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `POST /api/v1/payments` requires `X-API-Key` and `Idempotency-Key` headers; validates `amount` (Decimal > 0), `currency` (strict `RUB`/`USD`/`EUR` enum), `webhook_url` (valid `http(s)` URL, required); `description` and `metadata` are optional (`metadata` defaults to `{}`)
- [ ] `POST` creates the `Payment` row and the `Outbox` row in one transaction, returns `202 Accepted` with `payment_id`, `status`, `created_at`
- [ ] Outbox relay (background task in the API process) polls `outbox` via `SELECT ... FOR UPDATE SKIP LOCKED`, publishes to exchange `payments` / routing key `payments.new`, marks `published_at`
- [ ] Consumer handler receives a `payments.new` message, loads the `Payment` by id, runs Gateway emulation (`asyncio.sleep` 2-5s, 90% `succeeded` / 10% `failed`), persists `status` and `processed_at`
- [ ] Consumer sends a Webhook notification (`payment_id`, `status`, `amount`, `currency`, `processed_at`) to `webhook_url` with a 5s timeout — a single attempt, no retry logic yet
- [ ] `GET /api/v1/payments/{payment_id}` requires `X-API-Key`, returns the full `Payment` record or `404` if not found
- [ ] Structured JSON logs carry `payment_id` as a correlation key across API creation, outbox publish, consumer processing, and webhook send
- [ ] Unit tests for the three spec seams (happy path only): Payment service (creation), Outbox relay (`relay_once` picks up an unpublished row via a fake `publish`, marks `published_at`), Consumer handler (gateway emulation + webhook send via fakes)
