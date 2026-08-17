from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.identity import OrganizationMembership
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    ShelterVolunteerEntryReference,
    VolunteerAccessGrant,
    VolunteerApplication,
    VolunteerDecisionBatch,
    VolunteerDecisionBatchItem,
    VolunteerNotificationDelivery,
    VolunteerNotificationRetryBatch,
    VolunteerNotificationRetryBatchItem,
)
from sqlalchemy import CheckConstraint, UniqueConstraint


def _constraint_sql(model: type) -> str:
    values = []
    for constraint in model.__table__.constraints:
        if isinstance(constraint, CheckConstraint):
            values.append(str(constraint.sqltext))
        if isinstance(constraint, UniqueConstraint):
            values.append(",".join(column.name for column in constraint.columns))
    return " ".join(values)


def test_volunteer_access_models_have_expected_crm_tables_and_tenant_scope() -> None:
    models = (
        OrganizationVolunteerAccessPolicy,
        ShelterVolunteerEntryReference,
        VolunteerApplication,
        VolunteerAccessGrant,
        VolunteerDecisionBatch,
        VolunteerDecisionBatchItem,
        VolunteerNotificationDelivery,
        VolunteerNotificationRetryBatch,
        VolunteerNotificationRetryBatchItem,
    )
    assert len({model.__tablename__ for model in models}) == len(models)
    assert all("organization_id" in model.__table__.c for model in models)


def test_period_policy_retry_and_actor_constraints_are_declared() -> None:
    assert "default_grant_duration_hours > 0" in _constraint_sql(OrganizationVolunteerAccessPolicy)
    assert "expires_at > valid_from" in _constraint_sql(VolunteerAccessGrant)
    assert "attempt_count >= 0" in _constraint_sql(VolunteerNotificationDelivery)
    assert "actor_type" in AuditRecord.__table__.c
    assert "actor_reference" in AuditRecord.__table__.c
    assert "valid_from" in OrganizationMembership.__table__.c
    assert "expires_at" in OrganizationMembership.__table__.c
    assert "access_version" in OrganizationMembership.__table__.c


def test_batch_and_application_uniqueness_constraints_are_present() -> None:
    assert "organization_id,operation_id" in _constraint_sql(VolunteerDecisionBatch)
    assert "batch_id,application_id" in _constraint_sql(VolunteerDecisionBatchItem)
    assert "organization_id,operation_id" in _constraint_sql(VolunteerNotificationRetryBatch)
    assert "batch_id,notification_delivery_id" in _constraint_sql(
        VolunteerNotificationRetryBatchItem
    )
