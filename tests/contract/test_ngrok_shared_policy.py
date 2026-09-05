from pathlib import Path

import yaml
from scripts.generate_public_tunnel_config import generate_runtime_configs


def test_shared_policy_removes_then_sets_trusted_metadata(tmp_path: Path) -> None:
    result = generate_runtime_configs(
        profile_name="shared-demo-dev",
        output_dir=tmp_path,
        api_port=8001,
        web_port=3001,
        gateway_port=8082,
        runtime_origin="https://demo.example.test",
    )
    policy = yaml.safe_load(result.traffic_policy_path.read_text())
    rules = policy["on_http_request"]

    assert rules[0]["expressions"] == ['conn.client_ip == ""']
    assert rules[0]["actions"] == [{"type": "deny"}]
    actions = rules[1]["actions"]
    assert actions[0]["type"] == "remove-headers"
    assert set(actions[0]["config"]["headers"]) >= {
        "x-strayhub-trusted-client-ip",
        "x-strayhub-public-profile",
        "x-forwarded-for",
        "x-forwarded-proto",
    }
    assert actions[1] == {
        "type": "add-headers",
        "config": {
            "headers": {
                "x-strayhub-trusted-client-ip": "${conn.client_ip}",
                "x-strayhub-public-profile": "shared-demo-dev",
                "x-forwarded-proto": "https",
                "ngrok-skip-browser-warning": "true",
            }
        },
    }
    serialized = result.traffic_policy_path.read_text().lower()
    assert "authorization" not in serialized
    assert "password" not in serialized
