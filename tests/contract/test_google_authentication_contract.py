from pathlib import Path

import yaml
from scripts.generate_google_auth_contract import document


def test_google_contract_matches_runtime_schema_and_declares_restricted_account_operations():
    contract = yaml.safe_load(Path("specs/014-google-auth/contracts/openapi.yaml").read_text())
    assert contract == document()
    assert contract["paths"]["/v1/auth/google/transactions"]["post"]["security"] == []
    assert contract["security"] == [{"bearerAuth": []}]
    assert contract["components"]["schemas"]["TransactionRequest"]["additionalProperties"] is False
    assert "password" in contract["components"]["schemas"]["TransactionRequest"]["properties"]
    assert (
        contract["components"]["schemas"]["InvitationRequest"]["properties"]["role"]["pattern"]
        == "^(STAFF|SHELTER_ADMIN)$"
    )
