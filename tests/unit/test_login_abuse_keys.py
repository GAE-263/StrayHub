import pytest
from pydantic import SecretStr
from services.api.app.application.authentication.login_abuse import LoginAbuseKeys


def test_account_key_uses_nfkc_trim_casefold_without_changing_login_value() -> None:
    keys = LoginAbuseKeys(SecretStr("synthetic-login-abuse-secret-material"))
    submitted = "  ＳtaFF  "

    assert keys.account_digest(submitted) == keys.account_digest("staff")
    assert submitted == "  ＳtaFF  "


def test_account_and_ip_keys_use_domain_separation() -> None:
    keys = LoginAbuseKeys(SecretStr("synthetic-login-abuse-secret-material"))
    assert keys.account_digest("192.0.2.1") != keys.ip_digest("192.0.2.1")
    assert len(keys.account_digest("192.0.2.1")) == 64


def test_ipv4_and_ipv6_are_canonicalized_before_digesting() -> None:
    keys = LoginAbuseKeys(SecretStr("synthetic-login-abuse-secret-material"))
    assert keys.ip_digest("2001:0db8::1") == keys.ip_digest("2001:db8:0:0:0:0:0:1")
    assert len(keys.ip_digest("127.0.0.1")) == 64


def test_login_abuse_key_rejects_short_secret_without_exposing_it() -> None:
    secret = "short-secret"

    with pytest.raises(ValueError, match="too short") as caught:
        LoginAbuseKeys(SecretStr(secret))

    assert secret not in str(caught.value)
