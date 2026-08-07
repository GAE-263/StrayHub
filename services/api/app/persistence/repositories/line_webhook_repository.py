from services.api.app.persistence.repositories.line_identity_repository import (
    LineIdentityRepository,
)


class LineWebhookRepository(LineIdentityRepository):
    """Webhook 事件的語意別名；實際資料仍由共用 LINE Identity Repository 管理。"""
