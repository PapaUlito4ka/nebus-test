# 03 — Idempotency-Key conflict handling

**What to build:** Safe retries for the caller — resending the same `Idempotency-Key` never creates a duplicate `Payment`, and a key reused with a different body is rejected instead of silently applied.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] `POST` without an `Idempotency-Key` header returns `400`
- [ ] `POST` with a previously used `Idempotency-Key` and an identical body returns the same `payment_id`/`status`/`created_at` (replay) — no new row is created
- [ ] `POST` with a previously used `Idempotency-Key` and a different body returns `409 Conflict`
- [ ] Two concurrent identical requests with the same `Idempotency-Key` do not create duplicate `Payment` rows (unique constraint on `idempotency_key` + `IntegrityError` handling with re-read)
- [ ] Unit tests for the Payment service seam covering replay, conflict, and the concurrent-race scenario
