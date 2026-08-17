from services.api.app.application.volunteer_batch_service import chunk_targets
from tests.fixtures.volunteer_access import batch_application_fixtures


def test_100_manual_and_1200_all_filtered_targets_are_complete_without_duplicates() -> None:
    manual = batch_application_fixtures(100, code="ORG-A")
    all_filtered = batch_application_fixtures(1200, code="ORG-A", start=2000)
    assert len(manual) == 100
    chunks = list(chunk_targets(all_filtered))
    assert [len(chunk) for chunk in chunks] == [500, 500, 200]
    flattened = [item["id"] for chunk in chunks for item in chunk]
    assert len(flattened) == len(set(flattened)) == 1200
