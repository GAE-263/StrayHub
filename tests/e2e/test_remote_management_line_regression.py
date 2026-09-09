from pathlib import Path

import pytest

from tests.e2e.test_remote_management_tunnel_boundary import gateway, request


@pytest.mark.parametrize("profile", ["line-only", "shared-demo-production"])
def test_phase_e_line_journey_remains_reachable(profile: str, tmp_path: Path) -> None:
    animal = "00000000-0000-4000-8000-000000000000"
    with gateway(profile, tmp_path) as port:
        assert request(port, "POST", "/v1/line/webhook") == 200
        assert request(port, "GET", "/volunteer-entry") == 200
        assert request(port, "POST", "/v1/auth/liff/exchange") == 200
        assert request(port, "POST", "/v1/qr-tokens/resolve") == 200
        assert request(port, "GET", "/animal-confirmation") == 200
        assert request(port, "POST", f"/v1/animals/{animal}/confirm") == 200
        assert request(port, "GET", f"/v1/public/animals/{animal}/photo?token=cap") == 200
        assert request(port, "POST", "/v1/care-report-handoffs") == 200


def test_line_only_still_denies_all_management_entry_points(tmp_path: Path) -> None:
    with gateway("line-only", tmp_path) as port:
        assert request(port, "GET", "/login") == 404
        assert request(port, "POST", "/v1/auth/login") == 404
        assert request(port, "GET", "/v1/management/dashboard") == 404
