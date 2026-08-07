from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class AIProcessingJob(IdentityMixin, AuditMixin, Base):
    __tablename__ = "ai_processing_jobs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "job_type",
            "target_type",
            "target_id",
            "model_version",
            "prompt_version",
            "output_schema_version",
            name="uq_ai_job_target_version",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_enqueue", index=True)
    provider: Mapped[str] = mapped_column(String(120))
    model_name: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str] = mapped_column(String(200))
    prompt_template_id: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(120))
    output_schema_version: Mapped[str] = mapped_column(String(120))
    raw_ai_output: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    validation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
