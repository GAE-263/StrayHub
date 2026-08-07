from fastapi import FastAPI

from services.api.app.api.ai_observations import router as ai_observations_router
from services.api.app.api.animal_selection import router as animal_selection_router
from services.api.app.api.animal_timeline import router as animal_timeline_router
from services.api.app.api.authentication import router as authentication_router
from services.api.app.api.care_reports import router as care_reports_router
from services.api.app.api.errors import DomainError, domain_error_handler
from services.api.app.api.line_binding import router as line_binding_router
from services.api.app.api.line_drafts import router as line_drafts_router
from services.api.app.api.line_webhook import router as line_webhook_router
from services.api.app.api.media import router as media_router
from services.api.app.api.observation_options import router as observation_options_router
from services.api.app.api.organization_management import router as organization_management_router

app = FastAPI(title="StrayHub CRM Care Report API", version="0.1.0")
app.add_exception_handler(DomainError, domain_error_handler)
app.include_router(authentication_router)
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
