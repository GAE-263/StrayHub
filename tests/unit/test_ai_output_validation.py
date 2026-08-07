import pytest
from services.api.app.api.errors import DomainError
from services.worker.app.handlers.ai_validation import validate_ai_output


def test_ai_output_requires_allowed_descriptive_codes() -> None:
    result = validate_ai_output(
        {"observations": [{"code": "appearance.changed", "description": "外觀與平常不同"}]},
        allowed_codes={"appearance.changed"},
    )

    assert result["observations"][0]["code"] == "appearance.changed"


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
