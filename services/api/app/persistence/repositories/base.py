from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.domain.tenant_context import TenantContext


class ScopedRepository:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def require_scope(self, organization_id: UUID) -> None:
        if self.context.platform_scope:
            return
        if self.context.organization_id != organization_id:
            raise DomainError("organization_access_denied", "無法存取此收容所資料", 404)
