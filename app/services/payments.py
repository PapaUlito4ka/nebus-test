from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency, OutboxEntry, Payment


class IdempotencyKeyConflict(Exception):
    """Raised when an Idempotency-Key is reused with a different request body."""

    def __init__(self, existing_payment: Payment) -> None:
        self.existing_payment = existing_payment
        super().__init__(f"idempotency key {existing_payment.idempotency_key!r} already used with a different body")


def _matches(
    payment: Payment,
    *,
    amount: Decimal,
    currency: Currency,
    webhook_url: str,
    description: str | None,
    metadata: dict[str, Any],
) -> bool:
    return (
        payment.amount == amount
        and payment.currency == currency
        and payment.webhook_url == webhook_url
        and payment.description == description
        and payment.metadata_ == metadata
    )


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
    metadata = metadata or {}
    payment = Payment(
        amount=amount,
        currency=currency,
        description=description,
        metadata_=metadata,
        idempotency_key=idempotency_key,
        webhook_url=webhook_url,
    )
    session.add(payment)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing_payment = (
            await session.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        if existing_payment is None:
            raise
        if not _matches(
            existing_payment,
            amount=amount,
            currency=currency,
            webhook_url=webhook_url,
            description=description,
            metadata=metadata,
        ):
            raise IdempotencyKeyConflict(existing_payment) from None
        return existing_payment

    session.add(OutboxEntry(payload={"payment_id": str(payment.id)}))
    await session.commit()
    return payment
