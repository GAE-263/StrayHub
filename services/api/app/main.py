import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from sqlalchemy.exc import SQLAlchemyError

from services.api.app.api.adoption_inbox import router as adoption_inbox_router
from services.api.app.api.ai_observations import router as ai_observations_router
from services.api.app.api.animal_selection import router as animal_selection_router
from services.api.app.api.animal_timeline import router as animal_timeline_router
from services.api.app.api.assigned_care import router as assigned_care_router
from services.api.app.api.audit import router as audit_router
from services.api.app.api.authentication import router as authentication_router
from services.api.app.api.care_reminders import router as care_reminders_router
from services.api.app.api.care_report_handoffs import router as care_report_handoffs_router
from services.api.app.api.care_reports import router as care_reports_router
from services.api.app.api.dashboard import router as dashboard_router
from services.api.app.api.errors import (
    DomainError,
    domain_error_handler,
    request_validation_error_handler,
    sqlalchemy_error_handler,
)
from services.api.app.api.growth_diary import router as growth_diary_router
from services.api.app.api.line_binding import router as line_binding_router
from services.api.app.api.line_drafts import router as line_drafts_router
from services.api.app.api.line_webhook import router as line_webhook_router
from services.api.app.api.management_animals import router as management_animals_router
from services.api.app.api.media import router as media_router
from services.api.app.api.medical_records import router as medical_records_router
from services.api.app.api.observation_options import router as observation_options_router
from services.api.app.api.organization_management import router as organization_management_router
from services.api.app.api.platform_admin_management import (
    router as platform_admin_management_router,
)
from services.api.app.api.qr_codes import router as qr_codes_router
from services.api.app.api.report_inbox import router as report_inbox_router
from services.api.app.api.reportable_scope import router as reportable_scope_router
from services.api.app.api.volunteer_access import router as volunteer_access_router
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectScope
from services.api.app.observability.logging import get_logger

_logger = get_logger(__name__)


async def _warm_up_object_storage_client() -> None:
    """boto3/botocore lazily loads and parses its S3 service-model JSON the
    first time any S3 API method is called in a process — measured at
    several seconds on a cold WSL2 bind-mount. Pay that cost once here,
    fire-and-forget at startup, instead of on whichever real request
    happens to be first — e.g. the LINE adoption bot's first animal-photo
    lookup, which sits inside a tight reply-token window and has no room
    for a multi-second surprise. `generate_presigned_url` is a pure local
    signature computation (no network call), so a made-up scope/key here
    has no real side effects."""
    try:
        await MinioStorageAdapter().signed_url(
            scope=ObjectScope(uuid4()), key="warmup", expires_seconds=1
        )
    except Exception:
        _logger.exception("object_storage_warmup_failed")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    asyncio.create_task(_warm_up_object_storage_client())
    yield


app = FastAPI(title="StrayHub CRM Care Report API", version="0.1.0", lifespan=_lifespan)


def _custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "RS256 簽署的短效 Access Token；"
            "每次受保護 Request 仍必須通過 Server-side Session 與 Organization Scope 驗證。"
        ),
    }
    schema["security"] = [{"bearerAuth": []}]
    schema.setdefault("paths", {}).get("/healthz", {}).get("get", {})["security"] = []
    public_directory = (
        schema.setdefault("paths", {}).get("/v1/public/volunteer-organizations", {}).get("get", {})
    )
    public_directory["responses"].pop("401", None)
    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi
app.add_exception_handler(DomainError, domain_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_error_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
app.include_router(authentication_router)
app.include_router(dashboard_router)
app.include_router(management_animals_router)
app.include_router(report_inbox_router)
app.include_router(reportable_scope_router)
app.include_router(qr_codes_router)
app.include_router(audit_router)
app.include_router(animal_selection_router)
app.include_router(care_report_handoffs_router)
app.include_router(care_reports_router)
app.include_router(animal_timeline_router)
app.include_router(ai_observations_router)
app.include_router(observation_options_router)
app.include_router(organization_management_router)
app.include_router(platform_admin_management_router)
app.include_router(line_webhook_router)
app.include_router(media_router)
app.include_router(line_binding_router)
app.include_router(line_drafts_router)
app.include_router(volunteer_access_router)
app.include_router(medical_records_router)
app.include_router(care_reminders_router)
app.include_router(assigned_care_router)
app.include_router(adoption_inbox_router)
app.include_router(growth_diary_router)


@app.get("/healthz", tags=["Health"], openapi_extra={"security": []})
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
