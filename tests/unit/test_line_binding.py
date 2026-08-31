import pytest
from services.api.app.api.line_binding import LineBindRequest, bind_line_identity


class RecordingLineBindingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def bind_line_identity(self, *, id_token: str, organization_id=None) -> dict:
        self.calls.append((id_token, organization_id))
        return {"user_id": "user", "session_id": "session"}


class RecordingSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_line_bind_uses_legacy_binding_flow_without_entry_reference() -> None:
    service = RecordingLineBindingService()
    session = RecordingSession()

    result = await bind_line_identity(LineBindRequest(id_token="line-token"), service, session)

    assert service.calls == [("line-token", None)]
    assert session.committed is True
    assert result == {"user_id": "user", "session_id": "session"}
