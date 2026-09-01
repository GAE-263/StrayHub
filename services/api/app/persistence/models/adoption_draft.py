from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class AdoptionDraft(IdentityMixin, AuditMixin, Base):
    __tablename__ = "adoption_drafts"

    opaque_token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Nullable unlike every other tenant-scoped table: the very first turn
    # (SELECTING_ORGANIZATION) happens before the adopter has picked a shelter.
    # See migration 0030's RLS policy comment before copying this pattern elsewhere.
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    adopter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    path: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_animal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("animals.id"), nullable=True, index=True
    )
    candidate_match_ids: Mapped[list] = mapped_column(JSON, default=list)
    # [{"animal_id": str, "score": float, "reasons": [str, ...]}, ...] — one
    # entry for the specific_animal path, up to top_n for recommend_me.
    match_results: Mapped[list] = mapped_column(JSON, default=list)
    current_step: Mapped[str] = mapped_column(
        String(50), default="selecting_organization", index=True
    )
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    reconfirmation_keys: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    last_interaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
