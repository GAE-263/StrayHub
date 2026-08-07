from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.authentication import LineIdentityVerifierPort
from services.api.app.persistence.models.identity import WebhookSession
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.line_identity_repository import (
    LineIdentityRepository,
)


class LineIdentityService:
    def __init__(
        self,
        repository: LineIdentityRepository,
        authentication: AuthenticationRepository,
        verifier: LineIdentityVerifierPort,
        *,
        session_ttl_seconds: int = 86400,
    ) -> None:
        self.repository = repository
        self.authentication = authentication
        self.verifier = verifier
        self.session_ttl_seconds = session_ttl_seconds

    async def resolve(self, id_token: str) -> WebhookSession:
        line_user_id = await self.verifier.verify(id_token)
        binding = await self.repository.binding(line_user_id)
        if binding is None:
            raise DomainError("line_binding_required", "請先完成 LINE 身分綁定", 403)
        user = await self.authentication.get_user(binding.user_id)
        if user is None or user.status != "active":
            raise DomainError("line_binding_invalid", "LINE 身分綁定無效", 403)
        memberships = await self.authentication.memberships(user.id, active_only=True)
        sessions = await self.repository.sessions(user.id)
        if len(sessions) > 1 or len(memberships) != 1:
            raise DomainError("shelter_context_required", "請在 LIFF 明確選擇收容所", 409)
        membership = memberships[0]
        organization = await self.authentication.get_organization(membership.organization_id)
        if organization is None or organization.status != "active":
            raise DomainError("organization_disabled", "收容所目前停用", 403)
        if sessions:
            session = sessions[0]
            if session.organization_id != organization.id:
                raise DomainError("shelter_context_required", "請在 LIFF 明確選擇收容所", 409)
            return session
        now = datetime.now(timezone.utc)
        return await self.repository.add(
            WebhookSession(
                user_id=user.id,
                organization_id=organization.id,
                status="active",
                expires_at=now + timedelta(seconds=self.session_ttl_seconds),
            )
        )
