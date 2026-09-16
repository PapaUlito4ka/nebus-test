import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models import Currency, OutboxEntry, Payment, PaymentStatus
from app.services.payments import IdempotencyKeyConflict, create_payment


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


async def test_create_payment_replays_identical_body_without_new_row(
    db_session: AsyncSession,
) -> None:
    first = await create_payment(
        db_session,
        idempotency_key="key-replay",
        amount=Decimal("10.00"),
        currency=Currency.USD,
        description="test payment",
        metadata={"order_id": "abc"},
        webhook_url="https://example.com/hook",
    )

    second = await create_payment(
        db_session,
        idempotency_key="key-replay",
        amount=Decimal("10.00"),
        currency=Currency.USD,
        description="test payment",
        metadata={"order_id": "abc"},
        webhook_url="https://example.com/hook",
    )

    assert second.id == first.id
    assert second.status == first.status
    assert second.created_at == first.created_at

    payments = (
        await db_session.execute(select(Payment).where(Payment.idempotency_key == "key-replay"))
    ).scalars().all()
    assert len(payments) == 1

    outbox_rows = (await db_session.execute(select(OutboxEntry))).scalars().all()
    assert len(outbox_rows) == 1


async def test_create_payment_raises_conflict_for_different_body(
    db_session: AsyncSession,
) -> None:
    await create_payment(
        db_session,
        idempotency_key="key-conflict",
        amount=Decimal("10.00"),
        currency=Currency.USD,
        webhook_url="https://example.com/hook",
    )

    with pytest.raises(IdempotencyKeyConflict):
        await create_payment(
            db_session,
            idempotency_key="key-conflict",
            amount=Decimal("99.00"),
            currency=Currency.USD,
            webhook_url="https://example.com/hook",
        )

    payments = (
        await db_session.execute(select(Payment).where(Payment.idempotency_key == "key-conflict"))
    ).scalars().all()
    assert len(payments) == 1


async def test_create_payment_concurrent_same_key_does_not_duplicate(
    db_session: AsyncSession,
    db_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with session_factory() as second_session:
        first, second = await asyncio.gather(
            create_payment(
                db_session,
                idempotency_key="key-race",
                amount=Decimal("10.00"),
                currency=Currency.USD,
                webhook_url="https://example.com/hook",
            ),
            create_payment(
                second_session,
                idempotency_key="key-race",
                amount=Decimal("10.00"),
                currency=Currency.USD,
                webhook_url="https://example.com/hook",
            ),
        )

    assert first.id == second.id

    payments = (
        await db_session.execute(select(Payment).where(Payment.idempotency_key == "key-race"))
    ).scalars().all()
    assert len(payments) == 1
