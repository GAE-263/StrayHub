from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.line_wif_contract import EXPECTED, ContractError, validate


def test_reviewed_future_contract_is_exact() -> None:
    validate(Path("infra/gce/line-publication-wif-contract.json"))


def test_contract_rejects_broader_identity_or_permissions(tmp_path: Path) -> None:
    for field, value in (
        ("actor", "*"),
        ("ref", "refs/heads/main"),
        ("allowed_permissions", [*EXPECTED["allowed_permissions"], "storage.objects.delete"]),
    ):
        candidate = dict(EXPECTED)
        candidate[field] = value
        path = tmp_path / f"{field}.json"
        path.write_text(json.dumps(candidate), encoding="utf-8")
        with pytest.raises(ContractError):
            validate(path)
