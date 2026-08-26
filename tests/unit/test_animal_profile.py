from datetime import date

import pytest
from pydantic import ValidationError
from services.api.app.domain.animal_profile import AnimalProfile, AnimalProfileUpdate
from services.api.app.persistence.models.animal import Animal


def test_profile_defaults_preserve_legacy_animals() -> None:
    profile = AnimalProfile()
    assert profile.sex == "unknown"
    assert profile.birth_date is None
    assert profile.birth_date_estimated is False
    assert set(AnimalProfile.model_fields) <= set(Animal.__table__.columns.keys())


@pytest.mark.parametrize("sex", ["male", "female", "unknown"])
def test_sex_is_constrained(sex) -> None:
    assert AnimalProfile(sex=sex).sex == sex


@pytest.mark.parametrize(
    "values",
    [
        {"sex": "公"},
        {"sex": None},
        {"breed": "  "},
        {"breed": "a" * 121},
        {"age_description": "a" * 121},
        {"behavior_notes": "a" * 4001},
        {"care_guidance": "a" * 4001},
        {"birth_date": "invalid"},
        {"birth_date": "2020-02-02", "intake_date": "2020-02-01"},
        {"birth_date_estimated": True},
        {"organization_id": "untrusted"},
    ],
)
def test_invalid_profile_is_rejected(values) -> None:
    with pytest.raises(ValidationError):
        AnimalProfile(**values)


def test_profile_trims_text_preserves_lines_and_uses_dates() -> None:
    profile = AnimalProfile(
        breed=" 藏獒 ",
        behavior_notes=" 親人\n愛玩 ",
        birth_date="2020-02-01",
        intake_date="2020-02-01",
    )
    assert profile.breed == "藏獒"
    assert profile.behavior_notes == "親人\n愛玩"
    assert profile.birth_date == date(2020, 2, 1)
    assert AnimalProfileUpdate(care_guidance=None).model_dump(exclude_unset=True) == {
        "care_guidance": None
    }
