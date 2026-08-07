from pathlib import Path

import yaml

CONTRACT_PATH = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")
REQUIRED_ANSWER_KEYS = {
    "care_completion",
    "walk_completion",
    "feeding",
    "water",
    "activity",
    "urination",
    "defecation",
    "resource_guarding",
    "human_interaction",
    "animal_interaction",
    "emotion",
    "walk_reaction",
    "appearance_special_status",
}


def test_line_care_report_contract_covers_all_bot_and_liff_boundaries() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    paths = document["paths"]
    required_paths = {
        "/v1/line/webhook",
        "/v1/line/bind",
        "/v1/line/rich-menu/context",
        "/v1/line/care-report/drafts/current",
        "/v1/line/care-report/drafts/{draftId}/resume",
        "/v1/line/care-report/drafts/{draftId}/cancel",
        "/v1/care-report-drafts",
        "/v1/media",
        "/v1/care-reports",
    }
    assert required_paths <= paths.keys()
    assert paths["/v1/line/webhook"]["post"]["security"] == []
    assert paths["/v1/line/bind"]["post"]["security"] == []


def test_draft_answers_are_partial_but_formal_report_answers_are_complete() -> None:
    schemas = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))["components"]["schemas"]
    draft = schemas["DraftAnswers"]
    complete = schemas["CareReportAnswers"]

    assert not draft.get("required")
    assert REQUIRED_ANSWER_KEYS <= set(complete["allOf"][1]["required"])
    assert (
        schemas["CareReportCreateRequest"]["properties"]["observations"]["$ref"]
        == "#/components/schemas/CareReportAnswers"
    )


def test_webhook_contract_requires_event_identity_and_idempotency_header() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    event = document["components"]["schemas"]["LineWebhookEvent"]
    assert {"type", "webhookEventId", "timestamp", "source"} <= set(event["required"])
    report_create = document["paths"]["/v1/care-reports"]["post"]
    assert any(
        parameter.get("$ref", "").endswith("/IdempotencyKey")
        for parameter in report_create["parameters"]
    )
