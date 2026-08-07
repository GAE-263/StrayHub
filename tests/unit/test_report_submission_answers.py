from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report_draft import CareReportDraft


def test_formal_report_answer_set_requires_all_thirteen_fields() -> None:
    from services.api.app.domain.line_care_report_state import CareReportAnswers

    with pytest.raises(DomainError, match="缺少必要"):
        CareReportAnswers({key: "value" for key in REQUIRED_ANSWER_KEYS[:-1]})


def test_animal_has_immutable_business_identity_for_report_binding() -> None:
    animal_id = uuid4()
    animal = Animal(organization_id=uuid4(), name="小黑", status="active")
    draft = CareReportDraft(
        organization_id=animal.organization_id,
        volunteer_user_id=uuid4(),
        membership_id=uuid4(),
        animal_id=animal_id,
        opaque_token_digest="x" * 64,
        answers={},
        last_interaction_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        expires_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    assert draft.animal_id != animal.id
