from services.api.app.persistence.repositories.line_identity_repository import (
    LineIdentityRepository,
)


class LineWebhookRepository(LineIdentityRepository):
    """Webhook 事件的語意別名；實際資料仍由共用 LINE Identity Repository 管理。"""

    async def get_binding(self, line_user_id: str):
        return await self.binding(line_user_id)

    async def active_sessions(self, user_id):
        return await self.sessions(user_id)

    async def claim(self, **kwargs):
        return await self.claim_event(**kwargs)

    async def complete(self, event, **kwargs):
        return await self.complete_event(event, **kwargs)
