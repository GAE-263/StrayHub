import pytest
from services.api.app.api.errors import DomainError
from services.worker.app.handlers.ai_validation import validate_ai_output


def test_ai_output_requires_allowed_descriptive_codes() -> None:
    result = validate_ai_output(
        {"observations": [{"code": "appearance.changed", "description": "外觀與平常不同"}]},
        allowed_codes={"appearance.changed"},
    )

    assert result["observations"][0]["code"] == "appearance.changed"


def test_ai_output_requires_structured_observation_fields() -> None:
    with pytest.raises(DomainError):
        validate_ai_output(
            {"observations": [{"code": "appearance.changed", "description": 123}]},
            allowed_codes={"appearance.changed"},
        )


@pytest.mark.parametrize("key", ["score", "level", "status", "formal_status", "animal_id"])
def test_ai_output_cannot_produce_decision_or_identity_fields(key: str) -> None:
    with pytest.raises(DomainError):
        validate_ai_output({key: "forbidden", "observations": []}, allowed_codes=set())


@pytest.mark.parametrize(
    "output",
    [
        {"animal_id": "other-animal", "observations": []},
        {"observations": [{"code": "unknown.code"}]},
        {"observations": [{"code": "appearance.changed", "description": "需要就醫"}]},
    ],
)
def test_ai_output_cannot_change_identity_or_make_medical_decisions(output: dict) -> None:
    with pytest.raises(DomainError):
        validate_ai_output(output, allowed_codes={"appearance.changed"})
