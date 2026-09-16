from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.consumer import handle_payment
from app.models import Currency, Payment, PaymentStatus


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url: str, json: dict, timeout: float) -> "FakeResponse":
        self.calls.append((url, json))
        return FakeResponse(200)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


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
