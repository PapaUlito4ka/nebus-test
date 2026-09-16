import json
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue

EXCHANGE_NAME = "payments"
QUEUE_NAME = "payments.new"

Publish = Callable[[dict[str, Any]], Awaitable[None]]


async def declare_topology(channel: AbstractChannel) -> tuple[AbstractExchange, AbstractQueue]:
    exchange = await channel.declare_exchange(EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True)
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    await queue.bind(exchange, routing_key=QUEUE_NAME)
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
