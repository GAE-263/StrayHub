from fastapi import FastAPI

from services.api.app.api.ai_observations import router as ai_observations_router
from services.api.app.api.animal_selection import router as animal_selection_router
from services.api.app.api.animal_timeline import router as animal_timeline_router
from services.api.app.api.audit import router as audit_router
from services.api.app.api.authentication import router as authentication_router
from services.api.app.api.care_reports import router as care_reports_router
from services.api.app.api.dashboard import router as dashboard_router
from services.api.app.api.errors import DomainError, domain_error_handler
from services.api.app.api.line_binding import router as line_binding_router
from services.api.app.api.line_drafts import router as line_drafts_router
from services.api.app.api.line_webhook import router as line_webhook_router
from services.api.app.api.management_animals import router as management_animals_router
from services.api.app.api.media import router as media_router
from services.api.app.api.observation_options import router as observation_options_router
from services.api.app.api.organization_management import router as organization_management_router
from services.api.app.api.qr_codes import router as qr_codes_router
from services.api.app.api.report_inbox import router as report_inbox_router
from services.api.app.api.reportable_scope import router as reportable_scope_router

app = FastAPI(title="StrayHub CRM Care Report API", version="0.1.0")
app.add_exception_handler(DomainError, domain_error_handler)
app.include_router(authentication_router)
app.include_router(dashboard_router)
app.include_router(management_animals_router)
app.include_router(report_inbox_router)
app.include_router(reportable_scope_router)
app.include_router(qr_codes_router)
app.include_router(audit_router)
app.include_router(animal_selection_router)
app.include_router(care_reports_router)
app.include_router(animal_timeline_router)
app.include_router(ai_observations_router)
app.include_router(observation_options_router)
app.include_router(organization_management_router)
app.include_router(line_webhook_router)
app.include_router(media_router)
app.include_router(line_binding_router)
app.include_router(line_drafts_router)


@app.get("/healthz", tags=["Health"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
