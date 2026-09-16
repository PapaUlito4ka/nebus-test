import asyncio
import functools
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import aio_pika
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker import declare_topology
from app.config import settings
from app.db import async_session
from app.gateway import emulate_gateway
from app.logging_config import configure_logging
from app.models import Payment, PaymentStatus

logger = logging.getLogger(__name__)

Gateway = Callable[[], Awaitable[PaymentStatus]]


async def handle_payment(
    session: AsyncSession,
    gateway: Gateway,
    http_client: httpx.AsyncClient,
    payment_id: uuid.UUID,
) -> None:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        logger.warning("payment_not_found", extra={"payment_id": str(payment_id)})
        return

    payment.status = await gateway()
    payment.processed_at = datetime.now(UTC)
    await session.commit()
    logger.info(
        "gateway_emulation_done",
        extra={"payment_id": str(payment_id), "status": payment.status.value},
    )

    webhook_payload = {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
        "processed_at": payment.processed_at.isoformat(),
    }
    response = await http_client.post(payment.webhook_url, json=webhook_payload, timeout=5.0)
    logger.info(
        "webhook_sent",
        extra={"payment_id": str(payment_id), "status_code": response.status_code},
    )


async def _on_message(
    message: aio_pika.abc.AbstractIncomingMessage, *, http_client: httpx.AsyncClient
) -> None:
    async with message.process():
        payload = json.loads(message.body)
        payment_id = uuid.UUID(payload["payment_id"])
        try:
            async with async_session() as session:
                await handle_payment(session, emulate_gateway, http_client, payment_id)
        except Exception:
            logger.exception("payment_processing_failed", extra={"payment_id": str(payment_id)})
            raise


async def main() -> None:
    configure_logging()
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        _, queue = await declare_topology(channel)
        async with httpx.AsyncClient() as http_client:
            await queue.consume(functools.partial(_on_message, http_client=http_client))
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
