from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency, OutboxEntry, PaymentStatus
from app.payments import create_payment


async def test_create_payment_writes_payment_and_outbox_row_in_one_transaction(
    db_session: AsyncSession,
) -> None:
    payment = await create_payment(
        db_session,
        idempotency_key="key-1",
        amount=Decimal("42.50"),
        currency=Currency.USD,
        description="test payment",
        metadata={"order_id": "abc"},
        webhook_url="https://example.com/hook",
    )

    assert payment.id is not None
    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == Decimal("42.50")
    assert payment.created_at is not None

    outbox_rows = (await db_session.execute(select(OutboxEntry))).scalars().all()
    assert len(outbox_rows) == 1
    assert outbox_rows[0].payload == {"payment_id": str(payment.id)}
    assert outbox_rows[0].published_at is None
