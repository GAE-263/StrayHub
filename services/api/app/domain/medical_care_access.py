from __future__ import annotations

from dataclasses import dataclass

from services.api.app.api.errors import DomainError


@dataclass(frozen=True)
class MedicalCarePermission:
    can_view: bool
    can_manage_records: bool
    can_manage_series: bool
    can_process_occurrences: bool
    assigned_only: bool = False


def permission_for(
    *, role: str, membership_active: bool, medical_care_access: bool
) -> MedicalCarePermission:
    if not membership_active:
        return MedicalCarePermission(False, False, False, False)
    if role in {"PLATFORM_ADMIN", "SHELTER_ADMIN"}:
        return MedicalCarePermission(True, True, True, True)
    if role == "STAFF" and medical_care_access:
        return MedicalCarePermission(True, True, False, True)
    if role == "VOLUNTEER":
        return MedicalCarePermission(False, False, False, False, assigned_only=True)
    return MedicalCarePermission(False, False, False, False)


def require_medical_view(permission: MedicalCarePermission) -> None:
    if not permission.can_view:
        raise DomainError("medical_care_access_denied", "目前帳號無權查看醫療資料", 403)


def require_record_write(permission: MedicalCarePermission) -> None:
    require_medical_view(permission)
    if not permission.can_manage_records:
        raise DomainError("medical_care_write_denied", "目前帳號無權維護醫療紀錄", 403)


def require_series_write(permission: MedicalCarePermission) -> None:
    require_medical_view(permission)
    if not permission.can_manage_series:
        raise DomainError("reminder_series_write_denied", "目前帳號無權管理提醒週期", 403)
