from dataclasses import dataclass
from uuid import UUID

from services.api.app.api.errors import DomainError


@dataclass(frozen=True)
class TenantContext:
    user_id: UUID
    organization_id: UUID | None
    role: str
    platform_scope: bool = False

    def require_organization(self, organization_id: UUID) -> None:
        if self.platform_scope:
            return
        if self.organization_id != organization_id:
            raise DomainError("organization_access_denied", "無法存取此收容所資料", 404)
