"""Application-level validation shared by medical record entry points."""

from __future__ import annotations

from decimal import Decimal

from services.api.app.api.errors import DomainError


def validate_medical_record_fields(*, title: str, content: str, weight_kg: Decimal | None) -> None:
    if not title.strip() or not content.strip():
        raise DomainError("medical_record_content_required", "標題與內容不得為空白", 422)
    if weight_kg is not None and weight_kg <= 0:
        raise DomainError("invalid_weight", "體重必須大於 0 公斤", 422)


class MedicalRecordService:
    """Small domain boundary retained for future media and revision workflows."""

    @staticmethod
    def validate(*, title: str, content: str, weight_kg: Decimal | None) -> None:
        validate_medical_record_fields(title=title, content=content, weight_kg=weight_kg)
