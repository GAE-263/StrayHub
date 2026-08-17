from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_batch_service import (
    MAX_BATCH_CHUNK_SIZE,
    merge_decision_period,
    terminal_batch_status,
    validate_explicit_items,
)

NOW = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)


def test_explicit_selection_is_unique_and_limited_to_500() -> None:
    assert len(validate_explicit_items([(uuid4(), 1)])) == 1
    with pytest.raises(DomainError, match="500"):
        validate_explicit_items([(uuid4(), 1) for _ in range(501)])
    application_id = uuid4()
    with pytest.raises(DomainError, match="重複"):
        validate_explicit_items([(application_id, 1), (application_id, 1)])
    assert MAX_BATCH_CHUNK_SIZE == 500


def test_common_and_per_item_period_merge_uses_frozen_policy_snapshot() -> None:
    valid_from, expires_at = merge_decision_period(
        now=NOW,
        policy_duration_hours=72,
        common_valid_from=None,
        common_expires_at=None,
        override_valid_from=NOW + timedelta(hours=1),
        override_expires_at=None,
    )
    assert valid_from == NOW + timedelta(hours=1)
    assert expires_at == valid_from + timedelta(hours=72)


def test_batch_status_reconciles_all_terminal_results() -> None:
    assert terminal_batch_status(100, succeeded=100, conflict=0, failed=0) == "completed"
    assert terminal_batch_status(100, succeeded=95, conflict=5, failed=0) == (
        "completed_with_errors"
    )
    assert terminal_batch_status(100, succeeded=20, conflict=0, failed=0) == "processing"
