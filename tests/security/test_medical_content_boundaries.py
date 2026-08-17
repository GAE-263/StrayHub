from pathlib import Path

from services.api.app.application.medical_record_service import MedicalRecordService


def test_weight_is_only_validated_and_never_used_for_dosage() -> None:
    MedicalRecordService.validate(title="量體重", content="人工紀錄", weight_kg=12.5)
    feature_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("services/api/app").rglob("*.py")
        if "medical" in path.name or "care_reminder" in path.name
    ).lower()
    for forbidden in ("calculate_dosage", "dose_recommendation", "drug_interaction"):
        assert forbidden not in feature_sources


def test_ui_and_api_do_not_claim_overdue_means_missed_medication() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (Path("apps/web/features/medical-care"), Path("services/api/app/api"))
        for path in root.rglob("*")
        if path.suffix in {".py", ".ts", ".tsx"}
    )
    assert "漏藥" not in sources
