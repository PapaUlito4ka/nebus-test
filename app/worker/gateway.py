import asyncio
import random

from app.models import PaymentStatus


async def emulate_gateway() -> PaymentStatus:
    await asyncio.sleep(random.uniform(2, 5))
    return PaymentStatus.SUCCEEDED if random.random() < 0.9 else PaymentStatus.FAILED
