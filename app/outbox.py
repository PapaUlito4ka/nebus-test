import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.broker import Publish
from app.models import OutboxEntry

logger = logging.getLogger(__name__)


async def relay_once(session: AsyncSession, publish: Publish) -> int:
    result = await session.execute(
        select(OutboxEntry).where(OutboxEntry.published_at.is_(None)).with_for_update(skip_locked=True)
    )
    entries = result.scalars().all()

    for entry in entries:
        await publish(entry.payload)
        entry.published_at = datetime.now(UTC)
        await session.commit()
        logger.info("outbox_entry_published", extra={"payment_id": entry.payload.get("payment_id")})

    return len(entries)


async def run_relay_loop(
    session_factory: async_sessionmaker[AsyncSession],
    publish: Publish,
    interval: float = 1.0,
) -> None:
    while True:
        try:
            async with session_factory() as session:
                await relay_once(session, publish)
        except Exception:
            logger.exception("outbox_relay_tick_failed")
        await asyncio.sleep(interval)
