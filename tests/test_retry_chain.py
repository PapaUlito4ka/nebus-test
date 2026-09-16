from app.retry_chain import DLQ_NAME, RETRY_QUEUE_NAMES, RetryHop, next_hop


def test_first_failure_goes_to_first_retry_queue() -> None:
    assert next_hop(0) == RetryHop(routing_key=RETRY_QUEUE_NAMES[0], next_attempt=1)


def test_escalates_with_attempt_count() -> None:
    for attempt, expected_queue in enumerate(RETRY_QUEUE_NAMES):
        assert next_hop(attempt) == RetryHop(routing_key=expected_queue, next_attempt=attempt + 1)


def test_after_all_levels_goes_to_dlq() -> None:
    exhausted = len(RETRY_QUEUE_NAMES)
    assert next_hop(exhausted) == RetryHop(routing_key=DLQ_NAME, next_attempt=exhausted + 1)
