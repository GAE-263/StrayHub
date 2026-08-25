from types import SimpleNamespace
from uuid import uuid4

from services.api.app.api.qr_codes import _payload


def test_animal_qr_deep_link_carries_only_candidate_organization_and_opaque_token() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    token = "opaque-qr-token"

    result = _payload(
        SimpleNamespace(
            id=uuid4(),
            organization_id=organization_id,
            animal_id=animal_id,
            status="active",
            revoked=False,
        ),
        token,
    )

    assert result["deep_link"] == (
        f"/animal-confirmation?organization_id={organization_id}&qr_token={token}"
    )
    assert result["token"] is None
    assert str(animal_id) not in result["deep_link"]
