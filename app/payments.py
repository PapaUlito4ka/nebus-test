from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency, OutboxEntry, Payment


async def create_payment(
    session: AsyncSession,
    *,
    idempotency_key: str,
    amount: Decimal,
    currency: Currency,
    webhook_url: str,
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Payment:
    payment = Payment(
        amount=amount,
        currency=currency,
        description=description,
        metadata_=metadata or {},
        idempotency_key=idempotency_key,
        webhook_url=webhook_url,
    )
    session.add(payment)
    await session.flush()

    session.add(OutboxEntry(payload={"payment_id": str(payment.id)}))
    await session.commit()
    return payment
