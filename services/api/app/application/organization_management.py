from __future__ import annotations

from datetime import datetime, timezone

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

    @staticmethod
    def require_platform(*, role: str, platform_scope: bool) -> None:
        if role != "PLATFORM_ADMIN" and not platform_scope:
            raise DomainError("platform_admin_required", "需要平台管理員權限", 403)

    @staticmethod
    def require_settings_admin(
        *, role: str, platform_scope: bool, current_organization_id, target_organization_id
    ) -> None:
        if role in {"PLATFORM_ADMIN"} or platform_scope:
            return
        if role != "SHELTER_ADMIN" or current_organization_id != target_organization_id:
            raise DomainError("organization_settings_denied", "無法管理此收容所設定", 403)

    @classmethod
    def require_update_permission(
        cls,
        *,
        role: str,
        platform_scope: bool,
        current_organization_id,
        target_organization_id,
        has_platform_field: bool,
    ) -> None:
        if has_platform_field:
            cls.require_platform(role=role, platform_scope=platform_scope)
            return
        cls.require_settings_admin(
            role=role,
            platform_scope=platform_scope,
            current_organization_id=current_organization_id,
            target_organization_id=target_organization_id,
        )

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
        if await self.repository.count_active_shelter_admins(organization_id) >= 2:
            raise DomainError(
                "shelter_admin_limit_reached",
                "收容所最多只能有兩名啟用中的管理員",
                409,
            )
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
        if (
            role == "SHELTER_ADMIN"
            and await self.repository.count_active_shelter_admins(organization_id) >= 2
        ):
            raise DomainError(
                "shelter_admin_limit_reached",
                "收容所最多只能有兩名啟用中的管理員",
                409,
            )
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
        if (
            role == "SHELTER_ADMIN"
            and await self.repository.count_active_shelter_admins(organization_id) >= 2
        ):
            raise DomainError(
                "shelter_admin_limit_reached",
                "收容所最多只能有兩名啟用中的管理員",
                409,
            )
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
        volunteer_authorization_status: str | None = None,
        expected_access_version: int | None = None,
    ):
        current_version = max(1, int(getattr(membership, "access_version", 0) or 0))
        if expected_access_version is not None and expected_access_version != current_version:
            raise DomainError(
                "membership_state_changed",
                "成員權限已由其他操作更新，請重新載入後再確認",
                409,
            )

        after_role = role if role is not None else membership.role
        after_status = status if status is not None else membership.status
        after_medical = (
            medical_care_access
            if medical_care_access is not None
            else getattr(membership, "medical_care_access", False)
        )
        if role is not None:
            if role not in {"SHELTER_ADMIN", "STAFF", "VOLUNTEER"}:
                raise DomainError("invalid_role", "收容所角色無效", 422)
            if role == "VOLUNTEER" and membership.role != "VOLUNTEER":
                raise DomainError(
                    "volunteer_access_flow_required",
                    "請使用志工報名與限時授權流程轉換志工權限",
                    422,
                )
        if status is not None:
            if status not in {"invited", "active", "disabled"}:
                raise DomainError("invalid_membership_status", "Membership 狀態無效", 422)
            if (
                status == "active"
                and after_role == "VOLUNTEER"
                and volunteer_authorization_status in {"expired", "revoked"}
            ):
                label = "已撤銷" if volunteer_authorization_status == "revoked" else "已過期"
                raise DomainError(
                    "volunteer_authorization_not_active",
                    f"志工授權{label}，請先完成新的志工授權流程",
                    409,
                )
        if after_role != "STAFF" and medical_care_access is True:
            raise DomainError("medical_care_access_staff_only", "醫療權限只能授予 STAFF", 422)
        if (
            after_role == "VOLUNTEER"
            and volunteer_authorization_status
            in {
                "expired",
                "revoked",
            }
            and after_status == "active"
        ):
            label = "已撤銷" if volunteer_authorization_status == "revoked" else "已過期"
            raise DomainError(
                "volunteer_authorization_not_active",
                f"志工授權{label}，請先完成新的志工授權流程",
                409,
            )

        if after_role == "SHELTER_ADMIN" and after_status == "active":
            other_admins = await self.repository.count_active_shelter_admins(
                membership.organization_id,
                exclude_membership_id=membership.id,
            )
            if other_admins >= 2:
                raise DomainError(
                    "shelter_admin_limit_reached",
                    "收容所最多只能有兩名啟用中的管理員",
                    409,
                )
        elif (
            membership.role == "SHELTER_ADMIN"
            and membership.status == "active"
            and not (after_role == "SHELTER_ADMIN" and after_status == "active")
        ):
            other_admins = await self.repository.count_active_shelter_admins(
                membership.organization_id,
                exclude_membership_id=membership.id,
            )
            if other_admins < 1:
                raise DomainError(
                    "last_shelter_admin",
                    "收容所至少需要一名啟用中的管理員",
                    409,
                )

        membership.role = after_role
        membership.status = after_status
        if medical_care_access is not None:
            membership.medical_care_access = after_medical
        if role is not None or status is not None or medical_care_access is not None:
            membership.access_version = current_version + 1
        return membership

    async def archive_membership(
        self, membership, *, actor_user_id, expected_access_version: int | None = None
    ):
        current_version = max(1, int(getattr(membership, "access_version", 0) or 0))
        if expected_access_version is not None and expected_access_version != current_version:
            raise DomainError(
                "membership_state_changed",
                "成員權限已由其他操作更新，請重新載入後再確認",
                409,
            )
        if membership.status == "archived":
            raise DomainError("membership_already_archived", "Membership 已封存", 409)
        if membership.user_id == actor_user_id:
            raise DomainError("membership_self_archive_denied", "不能封存目前登入中的帳號", 409)
        if membership.role == "SHELTER_ADMIN" and membership.status == "active":
            remaining_admins = await self.repository.count_active_shelter_admins(
                membership.organization_id,
                exclude_membership_id=membership.id,
            )
            if remaining_admins == 0:
                raise DomainError(
                    "last_shelter_admin",
                    "收容所至少需要一名啟用中的管理員",
                    409,
                )
        membership.archived_from_status = membership.status
        membership.status = "archived"
        membership.archived_at = datetime.now(timezone.utc)
        membership.archived_by_user_id = actor_user_id
        membership.access_version = current_version + 1
        return membership

    async def restore_membership(self, membership, *, expected_access_version: int | None = None):
        current_version = max(1, int(getattr(membership, "access_version", 0) or 0))
        if expected_access_version is not None and expected_access_version != current_version:
            raise DomainError(
                "membership_state_changed",
                "成員權限已由其他操作更新，請重新載入後再確認",
                409,
            )
        if membership.status != "archived":
            raise DomainError("membership_not_archived", "Membership 目前不是封存狀態", 409)
        previous_status = membership.archived_from_status or "disabled"
        if membership.role == "VOLUNTEER":
            now = datetime.now(timezone.utc)
            if membership.expires_at is not None and membership.expires_at <= now:
                previous_status = "expired"
        if membership.role == "SHELTER_ADMIN" and previous_status == "active":
            other_admins = await self.repository.count_active_shelter_admins(
                membership.organization_id,
                exclude_membership_id=membership.id,
            )
            if other_admins >= 2:
                raise DomainError(
                    "shelter_admin_limit_reached",
                    "收容所最多只能有兩名啟用中的管理員",
                    409,
                )
        membership.status = previous_status
        membership.archived_from_status = None
        membership.archived_at = None
        membership.archived_by_user_id = None
        membership.access_version = current_version + 1
        return membership
