from datetime import datetime, timezone
from uuid import uuid4

from services.api.app.persistence.models.volunteer_access import VolunteerApplicationProfile
from sqlalchemy import ForeignKeyConstraint, LargeBinary, Text


def test_volunteer_application_profile_contains_only_encrypted_pii_storage() -> None:
    organization_id = uuid4()
    application_id = uuid4()
    deadline = datetime(2027, 1, 1, tzinfo=timezone.utc)

    profile = VolunteerApplicationProfile(
        organization_id=organization_id,
        application_id=application_id,
        applicant_name_ciphertext=b"encrypted-name",
        phone_ciphertext=b"encrypted-phone",
        pii_schema_version="v1",
        encryption_algorithm="AES-256-GCM",
        encryption_key_version="local-v1",
        retention_expires_at=deadline,
    )

    assert profile.organization_id == organization_id
    assert profile.application_id == application_id
    assert profile.retention_expires_at == deadline

    columns = VolunteerApplicationProfile.__table__.columns
    assert isinstance(columns["applicant_name_ciphertext"].type, LargeBinary)
    assert isinstance(columns["phone_ciphertext"].type, LargeBinary)
    assert columns["applicant_name_ciphertext"].nullable is True
    assert columns["phone_ciphertext"].nullable is True
    assert columns["application_id"].primary_key is True
    assert columns["pii_schema_version"].nullable is False
    assert isinstance(columns["encryption_key_version"].type, Text)
    assert isinstance(columns["basic_profile_ciphertext"].type, LargeBinary)
    assert columns["basic_profile_ciphertext"].nullable is True
    assert isinstance(columns["insurance_identity_ciphertext"].type, LargeBinary)
    assert columns["insurance_identity_ciphertext"].nullable is True
    assert columns["insurance_identity_delete_after"].nullable is True
    assert columns["pii_deleted_at"].nullable is True
    assert "applicant_name" not in columns
    assert "phone" not in columns
    assert "insurance_identity" not in columns
    constraints = {
        constraint.name for constraint in VolunteerApplicationProfile.__table__.constraints
    }
    assert "ck_volunteer_application_profiles_deleted_payload" in constraints
    assert "ck_volunteer_application_profiles_insurance_deadline" in constraints
    assert "ck_volunteer_application_profiles_retention_future" in constraints
    assert "ck_volunteer_application_profiles_encryption_metadata" in constraints
    indexes = {index.name for index in VolunteerApplicationProfile.__table__.indexes}
    assert indexes == {"ix_volunteer_application_profiles_org_retention"}
    foreign_keys = [
        constraint
        for constraint in VolunteerApplicationProfile.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]
    assert any(
        constraint.name == "fk_volunteer_application_profiles_application_scope"
        and [column.name for column in constraint.columns] == ["organization_id", "application_id"]
        for constraint in foreign_keys
    )
