from services.api.app.application.volunteer_access_service import VolunteerStatusResult


def test_onboarding_status_shape_cannot_contain_protected_resources_or_counts() -> None:
    fields = VolunteerStatusResult.__dataclass_fields__
    protected = {
        "animals",
        "drafts",
        "reports",
        "other_applicants",
        "matching_count",
        "membership",
    }
    assert protected.isdisjoint(fields)
