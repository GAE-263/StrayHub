from pathlib import Path


def test_grant_terminal_transitions_do_not_delete_source_care_data() -> None:
    service = Path("services/api/app/application/volunteer_access_service.py").read_text()
    expiration = Path("services/api/app/application/volunteer_expiration_service.py").read_text()
    assert ".delete(" not in service
    assert ".delete(" not in expiration
    assert "application_id" in service
    assert "previous_application_id" in service
