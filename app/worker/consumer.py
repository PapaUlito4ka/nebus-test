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

from app.core.config import settings
from app.core.db import async_session
from app.core.logging_config import configure_logging
from app.messaging.broker import declare_topology
from app.messaging.retry_chain import next_hop
from app.models import Payment, PaymentStatus
from app.worker.gateway import emulate_gateway

logger = logging.getLogger(__name__)

Gateway = Callable[[], Awaitable[PaymentStatus]]

TERMINAL_STATUSES = {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED}


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

    if payment.status in TERMINAL_STATUSES:
        logger.info(
            "gateway_emulation_skipped",
            extra={"payment_id": str(payment_id), "status": payment.status.value},
        )
    else:
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
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }
    response = await http_client.post(payment.webhook_url, json=webhook_payload, timeout=5.0)
    response.raise_for_status()
    logger.info(
        "webhook_sent",
        extra={"payment_id": str(payment_id), "status_code": response.status_code},
    )


RETRY_ATTEMPT_HEADER = "x-retry-attempt"


def _attempt_from_headers(headers: dict) -> int:
    attempt = headers.get(RETRY_ATTEMPT_HEADER, 0)
    return attempt if isinstance(attempt, int) else 0


async def _route_to_retry(
    exchange: aio_pika.abc.AbstractExchange,
    message: aio_pika.abc.AbstractIncomingMessage,
    payment_id: uuid.UUID,
) -> None:
    hop = next_hop(_attempt_from_headers(message.headers))
    headers = dict(message.headers)
    headers[RETRY_ATTEMPT_HEADER] = hop.next_attempt
    retry_message = aio_pika.Message(
        body=message.body,
        content_type=message.content_type,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        headers=headers,
    )
    await exchange.publish(retry_message, routing_key=hop.routing_key)
    logger.warning(
        "payment_processing_routed_to_retry",
        extra={"payment_id": str(payment_id), "routing_key": hop.routing_key},
    )


async def _on_message(
    message: aio_pika.abc.AbstractIncomingMessage,
    *,
    http_client: httpx.AsyncClient,
    exchange: aio_pika.abc.AbstractExchange,
) -> None:
    async with message.process():
        payload = json.loads(message.body)
        payment_id = uuid.UUID(payload["payment_id"])
        try:
            async with async_session() as session:
                await handle_payment(session, emulate_gateway, http_client, payment_id)
        except Exception:
            logger.exception("payment_processing_failed", extra={"payment_id": str(payment_id)})
            await _route_to_retry(exchange, message, payment_id)


async def main() -> None:
    configure_logging()
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        exchange, queue = await declare_topology(channel)
        async with httpx.AsyncClient() as http_client:
            await queue.consume(functools.partial(_on_message, http_client=http_client, exchange=exchange))
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
