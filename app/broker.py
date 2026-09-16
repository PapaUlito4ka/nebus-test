import json
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue

EXCHANGE_NAME = "payments"
QUEUE_NAME = "payments.new"
DLQ_NAME = "payments.new.dlq"
RETRY_QUEUE_NAMES = ["payments.retry.1", "payments.retry.2", "payments.retry.3"]
RETRY_TTLS_MS = [2_000, 8_000, 32_000]

Publish = Callable[[dict[str, Any]], Awaitable[None]]


async def declare_topology(channel: AbstractChannel) -> tuple[AbstractExchange, AbstractQueue]:
    exchange = await channel.declare_exchange(EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True)
    queue = await channel.declare_queue(
        QUEUE_NAME,
        durable=True,
        arguments={
            "x-dead-letter-exchange": EXCHANGE_NAME,
            "x-dead-letter-routing-key": RETRY_QUEUE_NAMES[0],
        },
    )
    await queue.bind(exchange, routing_key=QUEUE_NAME)

    for name, ttl_ms in zip(RETRY_QUEUE_NAMES, RETRY_TTLS_MS, strict=True):
        retry_queue = await channel.declare_queue(
            name,
            durable=True,
            arguments={
                "x-message-ttl": ttl_ms,
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": QUEUE_NAME,
            },
        )
        await retry_queue.bind(exchange, routing_key=name)

    dlq = await channel.declare_queue(DLQ_NAME, durable=True)
    await dlq.bind(exchange, routing_key=DLQ_NAME)

    return exchange, queue


def make_publisher(exchange: AbstractExchange) -> Publish:
    async def publish(payload: dict[str, Any]) -> None:
        message = aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await exchange.publish(message, routing_key=QUEUE_NAME)

    return publish
