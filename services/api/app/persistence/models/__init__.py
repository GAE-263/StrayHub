"""SQLAlchemy persistence models."""

from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.ai_observation import AICallLog, AIObservation
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.care_report import (
    CareReport,
    CareReportCorrection,
    CareReportMedia,
    MediaAsset,
    ReportIdempotencyKey,
)
from services.api.app.persistence.models.care_report_draft import CareReportDraft, DraftMediaAsset
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    LineWebhookEvent,
    Organization,
    OrganizationMembership,
    RefreshTokenRecord,
    SessionRecord,
    User,
    WebhookSession,
)
from services.api.app.persistence.models.observation import ObservationCategory, ObservationOption
from services.api.app.persistence.models.observation_usage import ObservationOptionUsage
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.models.reportable_scope import DailyReportableScope
from services.api.app.persistence.models.shelter_area import ShelterArea

__all__ = [
    "AIProcessingJob",
    "AIObservation",
    "AICallLog",
    "Animal",
    "AnimalQrCode",
    "AuditRecord",
    "CareReport",
    "CareReportCorrection",
    "CareReportDraft",
    "CareReportMedia",
    "DailyReportableScope",
    "DraftMediaAsset",
    "MediaAsset",
    "LineUserBinding",
    "LineWebhookEvent",
    "ObservationCategory",
    "ObservationOption",
    "ObservationOptionUsage",
    "Organization",
    "OrganizationMembership",
    "RefreshTokenRecord",
    "ReportIdempotencyKey",
    "SessionRecord",
    "User",
    "WebhookSession",
    "ShelterArea",
]
