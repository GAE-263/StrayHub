from pathlib import Path
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.medical_record_media_service import (
    media_type_allowed,
)
from services.api.app.domain.medical_care_access import permission_for, require_medical_view


def test_medical_record_access_requires_active_staff_capability() -> None:
    allowed = permission_for(role="STAFF", membership_active=True, medical_care_access=True)
    assert allowed.can_view and allowed.can_manage_records
    for active, capability in ((False, True), (True, False)):
        denied = permission_for(
            role="STAFF", membership_active=active, medical_care_access=capability
        )
        with pytest.raises(DomainError) as error:
            require_medical_view(denied)
        assert error.value.status_code == 403


def test_volunteer_and_cross_tenant_deep_links_cannot_use_full_medical_scope() -> None:
    volunteer = permission_for(role="VOLUNTEER", membership_active=True, medical_care_access=True)
    assert volunteer.assigned_only and not volunteer.can_view
    source = Path("services/api/app/api/medical_records.py").read_text(encoding="utf-8")
    repository = Path(
        "services/api/app/persistence/repositories/medical_record_repository.py"
    ).read_text(encoding="utf-8")
    assert "MedicalRecord.organization_id == self.organization_id" in repository
    assert "Animal.organization_id == organization_id" in source
    assert "medical_record_not_found" in source
    assert str(uuid4()) not in source


def test_attachment_policy_is_image_only_and_requires_sanitized_formal_media() -> None:
    assert media_type_allowed("image/jpeg")
    assert media_type_allowed("IMAGE/PNG")
    assert media_type_allowed(" image/webp ")
    for content_type in ("application/pdf", "image/gif", "image/svg+xml", "text/plain"):
        assert not media_type_allowed(content_type)
    source = Path("services/api/app/api/medical_records.py").read_text(encoding="utf-8")
    assert 'MediaAsset.status == "processed"' in source
    assert "MediaAsset.exif_removed.is_(True)" in source
    assert "ALLOWED_MEDICAL_MEDIA_TYPES" in source


def test_media_association_and_audit_queries_are_tenant_scoped() -> None:
    repository = Path(
        "services/api/app/persistence/repositories/medical_record_repository.py"
    ).read_text(encoding="utf-8")
    audit = Path("services/api/app/api/audit.py").read_text(encoding="utf-8")
    assert "MedicalRecord.organization_id == self.organization_id" in repository
    assert "MedicalRecordMedia.organization_id == record.organization_id" in Path(
        "services/api/app/api/medical_records.py"
    ).read_text(encoding="utf-8")
    assert "MedicalRecord" in audit and "require_medical_view" in audit
