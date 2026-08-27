"""Typed animal profile; management notes are not a volunteer projection."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

ShortProfileText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
ProfileNotes = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
AnimalSex = Literal["male", "female", "unknown"]


class AnimalProfileUpdate(BaseModel):
    """PATCH fields: omitted preserves; explicit null clears nullable fields."""

    model_config = ConfigDict(extra="forbid")

    sex: AnimalSex = "unknown"
    breed: ShortProfileText | None = None
    intake_date: date | None = None
    birth_date: date | None = None
    birth_date_estimated: bool = False
    age_description: ShortProfileText | None = None
    behavior_notes: ProfileNotes | None = None
    care_guidance: ProfileNotes | None = None


class AnimalProfile(AnimalProfileUpdate):
    @model_validator(mode="after")
    def validate_birth(self) -> Self:
        if self.birth_date and self.intake_date and self.birth_date > self.intake_date:
            raise ValueError("出生日期不得晚於入園日期")
        if self.birth_date_estimated and self.birth_date is None:
            raise ValueError("估計出生日期需要填寫出生日期")
        return self


def profile_values(animal: object) -> dict:
    return {
        name: getattr(animal, name, None)
        if field.default is None
        else getattr(animal, name, None) or field.default
        for name, field in AnimalProfile.model_fields.items()
    }
