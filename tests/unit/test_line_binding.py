import pytest
from services.api.app.api.line_binding import LineBindRequest, bind_line_identity


class RecordingLineBindingService:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    async def bind_line_identity(self, *, id_token: str) -> dict:
        self.tokens.append(id_token)
        return {"user_id": "user", "session_id": "session"}


@pytest.mark.asyncio
async def test_line_bind_uses_legacy_binding_flow_without_entry_reference() -> None:
    service = RecordingLineBindingService()

    result = await bind_line_identity(LineBindRequest(id_token="line-token"), service)

    assert service.tokens == ["line-token"]
    assert result == {"user_id": "user", "session_id": "session"}
