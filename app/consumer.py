import asyncio

import aio_pika

from app.config import settings


async def main() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
