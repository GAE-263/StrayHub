from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.domain.medical_care_access import MedicalCarePermission, permission_for
from services.api.app.persistence.models.identity import OrganizationMembership


async def medical_permission(
    session: AsyncSession, context: RequestContext
) -> MedicalCarePermission:
    if context.role in {"PLATFORM_ADMIN", "SHELTER_ADMIN"}:
        return permission_for(role=context.role, membership_active=True, medical_care_access=True)
    if context.organization_id is None or context.membership_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    membership = (
        await session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.id == context.membership_id,
                OrganizationMembership.organization_id == context.organization_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise DomainError("medical_care_access_denied", "目前帳號無權查看醫療資料", 403)
    return permission_for(
        role=context.role,
        membership_active=membership.status == "active",
        medical_care_access=membership.medical_care_access,
    )
