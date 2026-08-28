from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.line_rich_menu_routing import (
    RichMenuRoutingService,
    build_registry,
)
from services.api.app.application.ports.line_messaging import LineMessagingPort
from services.api.app.application.volunteer_access_service import VolunteerAccessService
from services.api.app.application.volunteer_batch_service import VolunteerBatchService
from services.api.app.application.volunteer_expiration_service import (
    VolunteerExpirationService,
)
from services.api.app.application.volunteer_notification_service import (
    VolunteerNotificationService,
)
from services.api.app.infrastructure.line.identity_verification_adapter import (
    LineIdentityVerifier,
)
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from services.worker.app.persistence.volunteer_access_repository import (
    WorkerVolunteerAccessRepository,
)


def _rich_menu_router() -> RichMenuRoutingService | None:
    """四個 richMenuId 都沒設定時回 None，選單退回即為 no-op。"""
    from services.api.app.config.settings import get_settings

    settings = get_settings()
    registry = build_registry(
        default=settings.line_rich_menu_default_id,
        volunteer=settings.line_rich_menu_volunteer_id,
        adopter=settings.line_rich_menu_adopter_id,
        staff=settings.line_rich_menu_staff_id,
    )
    if not registry.menu_ids:
        return None
    return RichMenuRoutingService(LineMessagingApiAdapter(), registry)


class VolunteerAccessHandler:
    def __init__(self, session: AsyncSession, *, worker_id: str) -> None:
        self.session = session
        self.worker_id = worker_id

    async def process_batch_chunk(self, organization_id: UUID, batch_id: UUID) -> object | None:
        worker_repository = WorkerVolunteerAccessRepository(
            self.session, organization_id, worker_id=self.worker_id
        )
        await worker_repository.recover_stale_claims()
        batch = await worker_repository.batch(batch_id)
        if batch is None or batch.status in {"completed", "completed_with_errors"}:
            return batch
        claimed_items = await worker_repository.claim_items(batch_id, limit=500)
        # Another worker may own the pending items, or a legacy batch may no
        # longer have any items. Do not reconcile an empty claim into an
        # invalid requested_count=0 batch; the next iteration can retry it.
        if not claimed_items:
            await self.session.rollback()
            return batch
        repository = VolunteerAccessRepository(self.session, organization_id)
        access_service = VolunteerAccessService(
            repository,
            AuthenticationRepository(self.session),
            LineIdentityVerifier("worker-does-not-verify-line-identity"),
            audit=AuditService(self.session),
            notifications=VolunteerNotificationService(repository),
        )
        await VolunteerBatchService(repository).process_pending_items(
            batch, access_service, limit=500, claimed_items=claimed_items
        )
        await self.session.commit()
        return batch

    async def deliver_notifications(
        self,
        organization_id: UUID,
        *,
        messaging: LineMessagingPort | None = None,
        limit: int = 100,
    ) -> int:
        worker_repository = WorkerVolunteerAccessRepository(
            self.session, organization_id, worker_id=self.worker_id
        )
        await worker_repository.recover_stale_notification_claims()
        deliveries = await worker_repository.claim_notifications(limit=limit)
        messenger = messaging or LineMessagingApiAdapter()
        for delivery in deliveries:
            line_user_id = await worker_repository.recipient_line_user_id(delivery.line_binding_id)
            if line_user_id is None:
                await worker_repository.complete_notification(
                    delivery,
                    sent=False,
                    error_code="recipient_unavailable",
                )
                continue
            payload = delivery.payload
            text = f"{payload.get('organization_name', '收容所')}：志工申請狀態已更新"
            if payload.get("application_status"):
                text += f"（{payload['application_status']}）"
            try:
                await messenger.push(
                    to_user_id=line_user_id,
                    messages=[{"type": "text", "text": text}],
                )
            except DomainError as exc:
                await worker_repository.complete_notification(
                    delivery,
                    sent=False,
                    transient=exc.status_code >= 500,
                    error_code=exc.code,
                )
            except Exception:
                await worker_repository.complete_notification(
                    delivery,
                    sent=False,
                    transient=True,
                    error_code="notification_provider_error",
                )
            else:
                await worker_repository.complete_notification(delivery, sent=True)
        await self.session.commit()
        return len(deliveries)

    async def expire_access(self, organization_id: UUID, *, limit: int = 500) -> int:
        await set_organization_scope(self.session, organization_id)
        repository = VolunteerAccessRepository(self.session, organization_id)
        changed = await VolunteerExpirationService(
            repository,
            AuthenticationRepository(self.session),
            audit=AuditService(self.session),
            notifications=VolunteerNotificationService(repository),
            rich_menu_router=_rich_menu_router(),
        ).sweep(limit=limit)
        await self.session.commit()
        return changed
