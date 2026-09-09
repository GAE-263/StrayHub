import pytest
from services.api.app.api.management_access import resolve_trusted_client_ip
from starlette.requests import Request


def request(*, host: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/auth/login",
            "headers": headers or [],
            "client": (host, 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_direct_mode_uses_socket_peer_and_ignores_forged_forwarding() -> None:
    value = resolve_trusted_client_ip(
        request(
            host="198.51.100.8",
            headers=[
                (b"x-forwarded-for", b"203.0.113.5"),
                (b"x-forwarded-proto", b"https"),
                (b"x-strayhub-trusted-client-ip", b"192.0.2.9"),
            ],
        ),
        trusted_proxy_enabled=False,
    )
    assert value == "198.51.100.8"


def test_proxy_mode_accepts_only_dedicated_header_from_loopback() -> None:
    value = resolve_trusted_client_ip(
        request(
            host="127.0.0.1",
            headers=[(b"x-strayhub-trusted-client-ip", b"2001:0db8::1")],
        ),
        trusted_proxy_enabled=True,
    )
    assert value == "2001:db8::1"


@pytest.mark.parametrize("peer", ["198.51.100.8", "203.0.113.9"])
def test_proxy_mode_rejects_dedicated_header_from_untrusted_peer(peer: str) -> None:
    with pytest.raises(ValueError, match="trusted client IP unavailable"):
        resolve_trusted_client_ip(
            request(
                host=peer,
                headers=[(b"x-strayhub-trusted-client-ip", b"192.0.2.1")],
            ),
            trusted_proxy_enabled=True,
        )


def test_local_test_peer_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="trusted client IP unavailable"):
        resolve_trusted_client_ip(
            request(host="testclient"),
            trusted_proxy_enabled=False,
        )

    assert (
        resolve_trusted_client_ip(
            request(host="testclient"),
            trusted_proxy_enabled=False,
            allow_local_test_peer=True,
        )
        == "127.0.0.1"
    )


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"x-forwarded-for", b"192.0.2.1")],
        [(b"x-strayhub-trusted-client-ip", b"invalid")],
        [
            (b"x-strayhub-trusted-client-ip", b"192.0.2.1"),
            (b"x-strayhub-trusted-client-ip", b"192.0.2.2"),
        ],
    ],
)
def test_proxy_mode_fails_closed_for_missing_invalid_or_duplicate_header(headers) -> None:
    with pytest.raises(ValueError, match="trusted client IP unavailable"):
        resolve_trusted_client_ip(
            request(host="::1", headers=headers),
            trusted_proxy_enabled=True,
        )
