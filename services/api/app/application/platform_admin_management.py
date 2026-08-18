from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.authentication import PasswordHasherPort
from services.api.app.persistence.models.identity import User
from services.api.app.persistence.repositories.platform_admin_repository import (
    PlatformAdminRepository,
)


@dataclass(frozen=True)
class PolicySummary:
    min_active_admins: int
    max_active_admins: int
    active_count: int

    @property
    def available_slots(self) -> int:
        return max(0, self.max_active_admins - self.active_count)


@dataclass(frozen=True)
class MutationResult:
    user: User
    action: str
    before: dict
    after: dict
    operation_id: UUID = field(default_factory=uuid4)


class PlatformAdminManagementService:
    def __init__(
        self,
        repository: PlatformAdminRepository,
        password_hasher: PasswordHasherPort,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher

    @staticmethod
    def _snapshot(user: User) -> dict:
        return {
            "user_id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "user_status": user.status,
            "platform_role": user.platform_role,
        }

    @staticmethod
    def _require_username(username: str) -> str:
        value = username.strip()
        if not value:
            raise DomainError("username_required", "帳號名稱不可為空", 422)
        return value

    @staticmethod
    def _require_password(password: str) -> str:
        value = password.strip()
        if not value:
            raise DomainError("temporary_password_required", "暫時密碼不可為空", 422)
        return value

    async def summary(self) -> PolicySummary:
        policy = await self.repository.policy()
        return PolicySummary(
            policy.min_active_admins,
            policy.max_active_admins,
            await self.repository.active_count(),
        )

    async def list_admins(self) -> tuple[list[User], PolicySummary]:
        admins = await self.repository.list_admins()
        policy = await self.repository.policy()
        count = sum(1 for admin in admins if admin.status == "active")
        return admins, PolicySummary(policy.min_active_admins, policy.max_active_admins, count)

    async def _locked(self):
        policy = await self.repository.lock_policy()
        count = await self.repository.active_count()
        return policy, count

    @staticmethod
    def _check_limit(count: int, max_count: int) -> None:
        if count >= max_count:
            raise DomainError(
                "platform_admin_limit_reached",
                "平台管理員已達兩位上限，請使用替換流程",
                409,
            )

    @staticmethod
    def _check_last(count: int, min_count: int) -> None:
        if count <= min_count:
            raise DomainError(
                "last_platform_admin",
                "平台至少需要一位啟用中的平台管理員",
                409,
            )

    async def create(
        self, *, username: str, display_name: str, temporary_password: str
    ) -> MutationResult:
        policy, count = await self._locked()
        username = self._require_username(username)
        password = self._require_password(temporary_password)
        if await self.repository.user_by_username(username) is not None:
            raise DomainError("username_exists", "帳號名稱已存在", 409)
        self._check_limit(count, policy.max_active_admins)
        user = await self.repository.add_user(
            User(
                username=username,
                display_name=display_name.strip() or username,
                password_hash=self.password_hasher.hash(password),
                status="active",
                platform_role="PLATFORM_ADMIN",
            )
        )
        return MutationResult(user, "platform_admin.created", {}, self._snapshot(user))

    async def promote(self, user_id: UUID) -> MutationResult:
        policy, count = await self._locked()
        user = await self.repository.user(user_id)
        if user is None:
            raise DomainError("user_not_found", "使用者不存在或不可揭露", 404)
        if user.status != "active":
            raise DomainError("account_not_eligible", "目標帳號目前停用", 409)
        if not (user.username or "").strip():
            raise DomainError("account_not_eligible", "目標帳號缺少可用帳號名稱", 409)
        if await self.repository.is_volunteer_account(user.id):
            raise DomainError(
                "account_not_eligible",
                "志工帳號不可直接提升為平台管理員",
                409,
            )
        if user.platform_role == "PLATFORM_ADMIN":
            raise DomainError("already_platform_admin", "目標帳號已是平台管理員", 409)
        self._check_limit(count, policy.max_active_admins)
        before = self._snapshot(user)
        user.platform_role = "PLATFORM_ADMIN"
        return MutationResult(user, "platform_admin.promoted", before, self._snapshot(user))

    async def enable(self, user_id: UUID) -> MutationResult:
        policy, count = await self._locked()
        user = await self.repository.user(user_id)
        if user is None or user.platform_role != "PLATFORM_ADMIN":
            raise DomainError("user_not_found", "平台管理員不存在或不可揭露", 404)
        if user.status == "active":
            raise DomainError("already_active", "平台管理員已啟用", 409)
        self._check_limit(count, policy.max_active_admins)
        before = self._snapshot(user)
        user.status = "active"
        return MutationResult(user, "platform_admin.enabled", before, self._snapshot(user))

    async def disable(self, user_id: UUID) -> MutationResult:
        policy, count = await self._locked()
        user = await self.repository.user(user_id)
        if user is None or user.platform_role != "PLATFORM_ADMIN":
            raise DomainError("user_not_found", "平台管理員不存在或不可揭露", 404)
        if user.status != "active":
            raise DomainError("already_disabled", "平台管理員已停用", 409)
        self._check_last(count, policy.min_active_admins)
        before = self._snapshot(user)
        user.status = "disabled"
        await self.repository.invalidate_sessions(user.id)
        return MutationResult(user, "platform_admin.disabled", before, self._snapshot(user))

    async def demote(self, user_id: UUID) -> MutationResult:
        policy, count = await self._locked()
        user = await self.repository.user(user_id)
        if user is None or user.platform_role != "PLATFORM_ADMIN":
            raise DomainError("user_not_found", "平台管理員不存在或不可揭露", 404)
        if user.status == "active":
            self._check_last(count, policy.min_active_admins)
        before = self._snapshot(user)
        user.platform_role = None
        await self.repository.invalidate_sessions(user.id)
        return MutationResult(user, "platform_admin.demoted", before, self._snapshot(user))

    async def replace(self, *, outgoing_user_id: UUID, replacement_user_id: UUID) -> MutationResult:
        policy, count = await self._locked()
        if outgoing_user_id == replacement_user_id:
            raise DomainError("platform_admin_replacement_invalid", "新舊帳號不可相同", 409)
        outgoing = await self.repository.user(outgoing_user_id)
        replacement = await self.repository.user(replacement_user_id)
        if (
            outgoing is None
            or outgoing.platform_role != "PLATFORM_ADMIN"
            or outgoing.status != "active"
            or replacement is None
            or replacement.status != "active"
            or not (replacement.username or "").strip()
            or replacement.platform_role == "PLATFORM_ADMIN"
        ):
            raise DomainError(
                "platform_admin_replacement_invalid",
                "替代帳號不符合啟用、角色或帳號安全條件",
                409,
            )
        if await self.repository.is_volunteer_account(replacement.id):
            raise DomainError(
                "platform_admin_replacement_invalid",
                "志工帳號不可直接替換為平台管理員",
                409,
            )
        if count < policy.min_active_admins or count > policy.max_active_admins:
            raise DomainError(
                "platform_admin_replacement_invalid", "目前平台管理員數量不符合政策", 409
            )
        before = {
            "outgoing": self._snapshot(outgoing),
            "replacement": self._snapshot(replacement),
        }
        replacement.platform_role = "PLATFORM_ADMIN"
        outgoing.platform_role = None
        await self.repository.invalidate_sessions(outgoing.id)
        after = {"outgoing": self._snapshot(outgoing), "replacement": self._snapshot(replacement)}
        return MutationResult(outgoing, "platform_admin.replaced", before, after)
