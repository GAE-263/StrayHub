from pathlib import Path

GENERATED_TYPES = Path("packages/contracts/src/openapi.ts")


def test_generated_contract_types_exist_for_openapi_source_of_truth() -> None:
    content = GENERATED_TYPES.read_text(encoding="utf-8")

    assert "export interface paths" in content
    assert "CareReportAnswers" in content
    assert "DraftAnswers" in content
