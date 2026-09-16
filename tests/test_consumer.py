import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.broker import DLQ_NAME, RETRY_QUEUE_NAMES
from app.consumer import RETRY_ATTEMPT_HEADER, _route_to_retry, handle_payment
from app.models import Currency, Payment, PaymentStatus

TEST_PAYMENT_ID = uuid.uuid4()


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url: str, json: dict, timeout: float) -> "FakeResponse":
        self.calls.append((url, json))
        return FakeResponse(200)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 300:
            raise RuntimeError(f"webhook responded with {self.status_code}")


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []
        self.published_headers: list[dict] = []

    async def publish(self, message, routing_key: str) -> None:  # noqa: ANN001
        self.published.append((routing_key, message.body))
        self.published_headers.append(dict(message.headers))


class FakeIncomingMessage:
    def __init__(self, body: bytes, attempt: int = 0) -> None:
        self.body = body
        self.content_type = "application/json"
        self.headers = {RETRY_ATTEMPT_HEADER: attempt} if attempt else {}


async def test_handle_payment_runs_gateway_and_sends_webhook(db_session: AsyncSession) -> None:
    payment = Payment(
        amount=Decimal("10.00"),
        currency=Currency.RUB,
        idempotency_key="consumer-test-key",
        webhook_url="https://example.com/hook",
    )
    db_session.add(payment)
    await db_session.commit()

    async def fake_gateway() -> PaymentStatus:
        return PaymentStatus.SUCCEEDED

    http_client = FakeHttpClient()

    await handle_payment(db_session, fake_gateway, http_client, payment.id)

    await db_session.refresh(payment)
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None

    assert len(http_client.calls) == 1
    url, sent_payload = http_client.calls[0]
    assert url == "https://example.com/hook"
    assert sent_payload == {
        "payment_id": str(payment.id),
        "status": "succeeded",
        "amount": "10.00",
        "currency": "RUB",
        "processed_at": payment.processed_at.isoformat(),
    }


async def test_handle_payment_skips_gateway_for_already_terminal_payment(db_session: AsyncSession) -> None:
    payment = Payment(
        amount=Decimal("10.00"),
        currency=Currency.RUB,
        idempotency_key="consumer-terminal-key",
        webhook_url="https://example.com/hook",
        status=PaymentStatus.SUCCEEDED,
        processed_at=datetime.now(UTC),
    )
    db_session.add(payment)
    await db_session.commit()

    async def gateway_must_not_run() -> PaymentStatus:
        raise AssertionError("gateway must not run for an already-terminal payment")

    http_client = FakeHttpClient()

    await handle_payment(db_session, gateway_must_not_run, http_client, payment.id)

    assert len(http_client.calls) == 1
    _, sent_payload = http_client.calls[0]
    assert sent_payload["status"] == "succeeded"


async def test_route_to_retry_first_failure_goes_to_first_retry_queue() -> None:
    exchange = FakeExchange()
    message = FakeIncomingMessage(b'{"payment_id": "x"}', attempt=0)

    await _route_to_retry(exchange, message, TEST_PAYMENT_ID)

    assert exchange.published == [(RETRY_QUEUE_NAMES[0], message.body)]


async def test_route_to_retry_escalates_with_attempt_count() -> None:
    for attempt, expected_queue in enumerate(RETRY_QUEUE_NAMES):
        exchange = FakeExchange()
        message = FakeIncomingMessage(b'{"payment_id": "x"}', attempt=attempt)

        await _route_to_retry(exchange, message, TEST_PAYMENT_ID)

        assert exchange.published == [(expected_queue, message.body)]


async def test_route_to_retry_after_all_levels_goes_to_dlq() -> None:
    exchange = FakeExchange()
    message = FakeIncomingMessage(b'{"payment_id": "x"}', attempt=len(RETRY_QUEUE_NAMES))

    await _route_to_retry(exchange, message, TEST_PAYMENT_ID)

    assert exchange.published == [(DLQ_NAME, message.body)]


async def test_route_to_retry_increments_attempt_header_for_next_hop() -> None:
    exchange = FakeExchange()
    message = FakeIncomingMessage(b'{"payment_id": "x"}', attempt=1)

    await _route_to_retry(exchange, message, TEST_PAYMENT_ID)

    assert exchange.published_headers[0][RETRY_ATTEMPT_HEADER] == 2
