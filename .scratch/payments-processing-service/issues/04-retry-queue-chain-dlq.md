# 04 — Retry queue chain + DLQ for webhook delivery failures

**What to build:** Resilience against a flaky or unreachable `webhook_url` — delivery failures are retried with exponential backoff through RabbitMQ's own redelivery (ADR-0001), and a payment already in a terminal state is never reprocessed by the Gateway emulation on redelivery, only its webhook is retried.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] RabbitMQ topology: `payments.retry.1` (TTL 2s), `payments.retry.2` (TTL 8s), `payments.retry.3` (TTL 32s), each with `x-dead-letter-exchange` routing back to `payments.new` once the TTL expires; final queue `payments.new.dlq`
- [ ] A webhook delivery failure (non-2xx response, network error, or timeout) routes the message to the next retry level based on the `x-death` header count, instead of acking it
- [ ] After the third failed attempt, the message lands in `payments.new.dlq`
- [ ] On redelivery, the Consumer checks the current `Payment` status first; if it's already terminal (`succeeded`/`failed`), it skips Gateway emulation and only retries the webhook send
- [ ] Unit tests for the Consumer handler seam covering idempotent redelivery (no gateway re-run on an already-terminal payment) and retry-level routing based on attempt count
