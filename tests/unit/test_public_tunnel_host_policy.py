import pytest
from scripts.public_tunnel_policy import (
    PolicyError,
    normalize_runtime_origin,
    runtime_host_matches,
)


def test_https_reserved_origin_is_normalized_for_exact_host_guard() -> None:
    origin = normalize_runtime_origin("https://Demo.Example.NGROK.APP:443")
    assert origin.origin == "https://demo.example.ngrok.app"
    assert origin.host == "demo.example.ngrok.app"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://demo.example.ngrok.app",
        "https://user@example.ngrok.app",
        "https://*.ngrok.app",
        "https://example.ngrok.app/path",
        "https://example.ngrok.app?x=1",
        "https://example.ngrok.app#fragment",
        "https://example.ngrok.app:8443",
        "https://example.ngrok.app.",
        "not-a-url",
    ],
)
def test_malformed_or_non_exact_public_origin_fails(value: str) -> None:
    with pytest.raises(PolicyError):
        normalize_runtime_origin(value)


def test_loopback_requires_explicit_local_validation_flag() -> None:
    with pytest.raises(PolicyError, match="loopback"):
        normalize_runtime_origin("http://127.0.0.1:8082")

    origin = normalize_runtime_origin("http://127.0.0.1:8082", allow_loopback_for_test=True)
    assert origin.host == "127.0.0.1:8082"
    assert origin.origin == "http://127.0.0.1:8082"


def test_idna_is_canonicalized_and_host_matching_is_exact() -> None:
    origin = normalize_runtime_origin("https://例子.example.ngrok.app")
    assert origin.hostname == "xn--fsqu00a.example.ngrok.app"
    assert runtime_host_matches(origin, "XN--FSQU00A.EXAMPLE.NGROK.APP")
    assert runtime_host_matches(origin, "xn--fsqu00a.example.ngrok.app:443")
    assert not runtime_host_matches(origin, "other.example.ngrok.app")
    assert not runtime_host_matches(origin, "xn--fsqu00a.example.ngrok.app:8443")
    assert not runtime_host_matches(origin, "user@xn--fsqu00a.example.ngrok.app")


def test_settings_exposes_runtime_only_reserved_origin_input() -> None:
    from services.api.app.config.settings import Settings

    settings = Settings(
        _env_file=None,
        public_tunnel_reserved_origin="https://reserved.example.ngrok.app",
    )
    assert settings.public_tunnel_reserved_origin == "https://reserved.example.ngrok.app"


def test_shared_profile_requires_runtime_origin() -> None:
    from scripts.public_tunnel_policy import compile_profile

    with pytest.raises(PolicyError, match="runtime origin"):
        compile_profile("shared-demo-dev")
