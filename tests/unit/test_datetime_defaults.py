from datetime import timedelta, timezone

from services.api.app.persistence.database.base import utc_now
from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.care_report import CareReport, CareReportCorrection
from services.api.app.persistence.models.identity import LineWebhookEvent, Organization


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    value = utc_now()

    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(0)


def test_timestamp_model_defaults_are_timezone_aware() -> None:
    timestamp_columns = (
        Organization.__table__.c.created_at,
        Organization.__table__.c.updated_at,
        LineWebhookEvent.__table__.c.received_at,
        CareReport.__table__.c.created_at,
        CareReportCorrection.__table__.c.created_at,
        AuditRecord.__table__.c.created_at,
    )

    for column in timestamp_columns:
        value = column.default.arg(None)
        assert value.tzinfo is not None
        assert value.astimezone(timezone.utc).utcoffset() == timedelta(0)
