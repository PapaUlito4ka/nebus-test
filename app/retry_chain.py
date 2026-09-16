from typing import NamedTuple

RETRY_QUEUE_NAMES = ["payments.retry.1", "payments.retry.2", "payments.retry.3"]
DLQ_NAME = "payments.new.dlq"


class RetryHop(NamedTuple):
    routing_key: str
    next_attempt: int


def next_hop(attempt: int) -> RetryHop:
    routing_key = RETRY_QUEUE_NAMES[attempt] if attempt < len(RETRY_QUEUE_NAMES) else DLQ_NAME
    return RetryHop(routing_key=routing_key, next_attempt=attempt + 1)
