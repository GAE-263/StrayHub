from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.database.scope import set_organization_scope


@dataclass
class MedicalAuditLifecycle:
    result: str = "success"


@asynccontextmanager
async def medical_care_audit_lifecycle(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID | None = None,
    reason: str | None = None,
) -> AsyncIterator[MedicalAuditLifecycle]:
    """Persist one terminal audit even when the protected transaction rolls back."""
    lifecycle = MedicalAuditLifecycle()
    failure: BaseException | None = None
    try:
        yield lifecycle
    except DomainError as exc:
        failure = exc
        lifecycle.result = "not_found" if exc.status_code == 404 else "denied"
        raise
    except Exception as exc:
        failure = exc
        lifecycle.result = "exception"
        raise
    finally:
        if failure is not None:
            await session.rollback()
            await set_organization_scope(session, organization_id)
        await AuditService(session).record(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            source_channel="api",
            reason=reason,
            result=lifecycle.result,
        )
        if failure is not None:
            await session.commit()
