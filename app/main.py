import asyncio
import contextlib
from collections.abc import AsyncIterator

import aio_pika
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.core.db import async_session
from app.core.logging_config import configure_logging
from app.messaging.broker import declare_topology, make_publisher
from app.services.outbox import run_relay_loop

configure_logging()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    exchange, _ = await declare_topology(channel)
    publish = make_publisher(exchange)
    relay_task = asyncio.create_task(run_relay_loop(async_session, publish))
    try:
        yield
    finally:
        relay_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await relay_task
        await connection.close()


app = FastAPI(title="Payments Processing Service", lifespan=lifespan)
app.include_router(router)
