from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin

if TYPE_CHECKING:
    from services.api.app.persistence.models.ai_job import AIProcessingJob


class AIObservation(IdentityMixin, AuditMixin, Base):
    __tablename__ = "ai_observations"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("ai_processing_jobs.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    raw_ai_output: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    validated_ai_observation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    human_review_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job: Mapped["AIProcessingJob"] = relationship("AIProcessingJob", lazy="joined")


class AICallLog(IdentityMixin, AuditMixin, Base):
    __tablename__ = "ai_call_logs"

    job_id: Mapped[UUID] = mapped_column(ForeignKey("ai_processing_jobs.id"), index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String(120))
    model_name: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(120))
    output_schema_version: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30))
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
