from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEntry
from app.services.outbox import relay_once


async def test_relay_once_publishes_unpublished_row_and_marks_it_published(
    db_session: AsyncSession,
) -> None:
    entry = OutboxEntry(payload={"payment_id": "abc-123"})
    db_session.add(entry)
    await db_session.commit()

    published_payloads = []

    async def fake_publish(payload: dict) -> None:
        published_payloads.append(payload)

    published_count = await relay_once(db_session, fake_publish)

    assert published_count == 1
    assert published_payloads == [{"payment_id": "abc-123"}]

    refreshed = (await db_session.execute(select(OutboxEntry))).scalar_one()
    assert refreshed.published_at is not None


async def test_relay_once_skips_already_published_rows(db_session: AsyncSession) -> None:
    from datetime import UTC, datetime

    entry = OutboxEntry(payload={"payment_id": "already-done"}, published_at=datetime.now(UTC))
    db_session.add(entry)
    await db_session.commit()

    calls = []

    async def fake_publish(payload: dict) -> None:
        calls.append(payload)

    published_count = await relay_once(db_session, fake_publish)

    assert published_count == 0
    assert calls == []
