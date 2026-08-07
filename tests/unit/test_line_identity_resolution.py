import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.line_identity_service import LineIdentityService


@pytest.mark.asyncio
async def test_multiple_memberships_require_explicit_shelter_context() -> None:
    class Verifier:
        async def verify(self, _token: str) -> str:
            return "line-user"

    class BindingRepo:
        async def binding(self, _line_user_id: str):
            return type("Binding", (), {"user_id": "user-id"})()

        async def sessions(self, _user_id):
            return []

    class AuthRepo:
        async def get_user(self, _user_id):
            return type("User", (), {"id": "user-id", "status": "active"})()

        async def memberships(self, _user_id, *, active_only=False):
            return [type("Membership", (), {})(), type("Membership", (), {})()]

    with pytest.raises(DomainError, match="明確選擇"):
        await LineIdentityService(BindingRepo(), AuthRepo(), Verifier()).resolve("id-token")
