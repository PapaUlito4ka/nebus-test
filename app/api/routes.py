import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.models import Payment
from app.schemas import PaymentCreate, PaymentCreateResponse, PaymentRead
from app.services.payments import IdempotencyKeyConflict, create_payment

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/api/v1/payments",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_api_key)],
)
async def create_payment_endpoint(
    body: PaymentCreate,
    session: SessionDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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


@router.get("/api/v1/payments/{payment_id}", dependencies=[Depends(verify_api_key)])
async def get_payment(payment_id: UUID, session: SessionDep) -> PaymentRead:
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
