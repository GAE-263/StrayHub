from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class CareReportDraft(IdentityMixin, AuditMixin, Base):
    __tablename__ = "care_report_drafts"

    opaque_token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    volunteer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    membership_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization_memberships.id"), index=True
    )
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    candidate_animal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("animals.id"), nullable=True, index=True
    )
    current_step: Mapped[str] = mapped_column(String(50), default="selecting_animal", index=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    answer_validation_version: Mapped[str] = mapped_column(String(40), default="v1")
    answer_source_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    modification_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    reconfirmation_keys: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    story: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    last_interaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DraftMediaAsset(IdentityMixin, Base):
    __tablename__ = "draft_media_assets"

    draft_id: Mapped[UUID] = mapped_column(ForeignKey("care_report_drafts.id"), index=True)
    media_asset_id: Mapped[UUID] = mapped_column(ForeignKey("media_assets.id"), index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
