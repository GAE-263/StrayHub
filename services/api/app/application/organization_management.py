from __future__ import annotations

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.authentication import PasswordHasherPort
from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from services.api.app.persistence.repositories.organization_repository import OrganizationRepository


class OrganizationManagementService:
    def __init__(
        self, repository: OrganizationRepository, password_hasher: PasswordHasherPort
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher

    async def create(self, *, code: str, name: str, initial_admin_user_id=None) -> Organization:
        organization = await self.repository.create_with_volunteer_policy(code=code, name=name)
        if initial_admin_user_id:
            await self.repository.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=initial_admin_user_id,
                    role="SHELTER_ADMIN",
                    status="active",
                )
            )
        return organization

    async def create_initial_admin(
        self, *, organization_id, username: str, temporary_password: str
    ) -> User:
        organization = await self.repository.get(organization_id)
        if organization is None or organization.status == "suspended":
            raise DomainError("organization_not_found", "收容所不存在或已停用", 404)
        if await self.repository.user_by_username(username) is not None:
            raise DomainError("username_exists", "帳號名稱已存在", 409)
        user = await self.repository.add(
            User(
                username=username,
                display_name=username,
                password_hash=self.password_hasher.hash(temporary_password),
                status="active",
            )
        )
        await self.repository.add(
            OrganizationMembership(
                organization_id=organization_id,
                user_id=user.id,
                role="SHELTER_ADMIN",
                status="active",
            )
        )
        return user

    async def create_account(
        self,
        *,
        organization_id,
        username: str,
        display_name: str,
        temporary_password: str,
        role: str,
    ) -> tuple[User, OrganizationMembership]:
        organization = await self.repository.get(organization_id)
        if organization is None or organization.status != "active":
            raise DomainError("organization_not_active", "收容所尚未啟用或已停用", 409)
        if await self.repository.user_by_username(username) is not None:
            raise DomainError("username_exists", "帳號名稱已存在", 409)
        user = await self.repository.add(
            User(
                username=username,
                display_name=display_name,
                password_hash=self.password_hasher.hash(temporary_password),
                status="active",
            )
        )
        membership = await self.create_membership(
            organization_id=organization_id,
            user_id=user.id,
            role=role,
        )
        return user, membership

    async def disable(self, organization_id) -> Organization:
        organization = await self.repository.get(organization_id)
        if organization is None:
            raise DomainError("organization_not_found", "收容所不存在", 404)
        organization.status = "suspended"
        return organization

    async def create_membership(
        self, *, organization_id, user_id, role: str
    ) -> OrganizationMembership:
        if role not in {"SHELTER_ADMIN", "STAFF", "VOLUNTEER"}:
            raise DomainError("invalid_role", "收容所角色無效", 422)
        if role == "VOLUNTEER":
            raise DomainError(
                "volunteer_access_flow_required",
                "請使用志工報名與限時授權流程建立志工權限",
                422,
            )
        organization = await self.repository.get(organization_id)
        user = await self.repository.user(user_id)
        if organization is None or user is None:
            raise DomainError("resource_not_found", "收容所或使用者不存在", 404)
        if organization.status != "active":
            raise DomainError("organization_not_active", "收容所尚未啟用或已停用", 409)
        if user.status != "active":
            raise DomainError("user_disabled", "使用者目前停用", 409)
        if await self.repository.membership(user_id, organization_id) is not None:
            raise DomainError("membership_exists", "此使用者已存在收容所 Membership", 409)
        return await self.repository.add(
            OrganizationMembership(
                organization_id=organization_id,
                user_id=user_id,
                role=role,
                status="active",
            )
        )

    async def update_membership(
        self,
        membership,
        *,
        role: str | None,
        status: str | None,
        medical_care_access: bool | None = None,
    ):
        if role is not None:
            if role not in {"SHELTER_ADMIN", "STAFF", "VOLUNTEER"}:
                raise DomainError("invalid_role", "收容所角色無效", 422)
            if role == "VOLUNTEER" and membership.role != "VOLUNTEER":
                raise DomainError(
                    "volunteer_access_flow_required",
                    "請使用志工報名與限時授權流程轉換志工權限",
                    422,
                )
            membership.role = role
        if status is not None:
            if status not in {"invited", "active", "disabled"}:
                raise DomainError("invalid_membership_status", "Membership 狀態無效", 422)
            membership.status = status
        if medical_care_access is not None:
            if membership.role != "STAFF":
                raise DomainError("medical_care_access_staff_only", "醫療權限只能授予 STAFF", 422)
            membership.medical_care_access = medical_care_access
        return membership
