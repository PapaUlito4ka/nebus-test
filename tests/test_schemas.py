from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import Currency
from app.schemas import PaymentCreate


def test_payment_create_accepts_two_decimal_places() -> None:
    payment = PaymentCreate(
        amount=Decimal("10.99"),
        currency=Currency.USD,
        webhook_url="https://example.com/hook",
    )

    assert payment.amount == Decimal("10.99")


def test_payment_create_rejects_more_than_two_decimal_places() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount=Decimal("10.999"),
            currency=Currency.USD,
            webhook_url="https://example.com/hook",
        )
