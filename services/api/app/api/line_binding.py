from fastapi import APIRouter, Depends
from pydantic import BaseModel
from services.api.app.api.authentication import get_session_service
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.session_service import SessionService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/line", tags=["LINE Bot"])


class LineBindRequest(BaseModel):
    id_token: str


@router.post("/bind", openapi_extra={"security": []})
async def bind_line_identity(
    payload: LineBindRequest,
    service: SessionService = Depends(get_session_service),  # noqa: B008
) -> dict:
    return await service.bind_line_identity(id_token=payload.id_token)


@router.get("/rich-menu/context")
async def rich_menu_context(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    _session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    return {
        "organization_id": context.organization_id,
        "actions": [
            "start_care_report",
            "list_reportable_animals",
            "resume_draft",
            "contact_staff",
        ],
    }
