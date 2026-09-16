import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from uuid import UUID

import aio_pika
from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker import declare_topology, make_publisher
from app.config import settings
from app.db import async_session, get_session
from app.logging_config import configure_logging
from app.models import Payment
from app.outbox import run_relay_loop
from app.payments import IdempotencyKeyConflict, create_payment
from app.schemas import PaymentCreate, PaymentCreateResponse, PaymentRead

configure_logging()
logger = logging.getLogger(__name__)


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


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/payments",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_api_key)],
)
async def create_payment_endpoint(
    body: PaymentCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> PaymentCreateResponse:
    if not idempotency_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key header is required")

    try:
        payment = await create_payment(
            session,
            idempotency_key=idempotency_key,
            amount=body.amount,
            currency=body.currency,
            description=body.description,
            metadata=body.metadata,
            webhook_url=str(body.webhook_url),
        )
    except IdempotencyKeyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key already used with a different request body",
        ) from exc

    logger.info("payment_created", extra={"payment_id": str(payment.id)})
    return PaymentCreateResponse(payment_id=payment.id, status=payment.status, created_at=payment.created_at)


@app.get("/api/v1/payments/{payment_id}", dependencies=[Depends(verify_api_key)])
async def get_payment(payment_id: UUID, session: AsyncSession = Depends(get_session)) -> PaymentRead:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment not found")
    return PaymentRead(
        payment_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.metadata_,
        status=payment.status,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )
