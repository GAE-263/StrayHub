from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from services.api.app.api import volunteer_access as api
from services.api.app.api.volunteer_access import VolunteerDecisionItemResponse


SENTINEL_NAME = "synthetic-applicant-name"
SENTINEL_PHONE = "synthetic-applicant-phone"
SENTINEL_CIPHERTEXT = "synthetic-ciphertext"
SENTINEL_LINE_TOKEN = "synthetic-line-token"


def _application():
    return SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        status="pending",
        submitted_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        decided_at=None,
        decision_reason=None,
        version=1,
    )


def test_normal_application_and_masked_detail_serializers_have_no_pii_boundary() -> None:
    application = _application()
    detail = SimpleNamespace(application=application, service_dates=[])

    list_payload = api._application_dict(application)
    detail_payload = api._application_detail_dict(detail)

    for payload in (list_payload, detail_payload):
        serialized = repr(payload)
        assert SENTINEL_NAME not in serialized
        assert SENTINEL_PHONE not in serialized
        assert SENTINEL_CIPHERTEXT not in serialized
        assert SENTINEL_LINE_TOKEN not in serialized
        assert set(payload) <= {
            "id",
            "organization_id",
            "display_name",
            "status",
            "submitted_at",
            "decided_at",
            "decision_reason",
            "version",
            "service_dates",
        }


def test_batch_decision_item_and_reveal_contracts_reject_pii_fields() -> None:
    item = VolunteerDecisionItemResponse.model_validate(
        {
            "application_id": str(uuid4()),
            "expected_version": 1,
            "result": "pending",
        }
    )
    assert "applicant_name" not in item.model_dump()
    assert "phone_number" not in item.model_dump()
    assert "ciphertext" not in item.model_dump()

    with pytest.raises(ValidationError):
        api.VolunteerPiiRevealResponse.model_validate(
            {
                "applicant_name": SENTINEL_NAME,
                "phone_number": SENTINEL_PHONE,
                "basic_profile": None,
                "ciphertext": SENTINEL_CIPHERTEXT,
            }
        )


def test_reveal_response_does_not_include_insurance_or_raw_identity_fields() -> None:
    response = api.VolunteerPiiRevealResponse(
        applicant_name=SENTINEL_NAME,
        phone_number=SENTINEL_PHONE,
        basic_profile={"experience": "synthetic"},
    )
    serialized = response.model_dump()
    assert set(serialized) == {"applicant_name", "phone_number", "basic_profile"}
    assert "insurance_identity" not in serialized
    assert "line_user_id" not in serialized
    assert "shelter_entry_reference" not in serialized
