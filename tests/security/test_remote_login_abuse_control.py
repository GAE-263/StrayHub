from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import SecretStr
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.login_abuse import (
    LoginAbuseKeys,
    LoginLimitDecision,
)
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.persistence.models.identity import (
    LoginAccountAbuseState,
    User,
)


class SpyHasher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, password: str, encoded_hash: str) -> bool:
        self.calls.append((password, encoded_hash))
        return encoded_hash == "real-hash" and password == "correct"

    def needs_rehash(self, encoded_hash: str) -> bool:
        return False


class FakeToken:
    def issue(self, claims) -> str:
        return "access-token"

    def verify(self, token: str):
        return {}


class AbuseRepository:
    def __init__(self, user: User | None) -> None:
        self.user = user
        self.account: dict[str, LoginAccountAbuseState] = {}
        self.ip_attempts: dict[str, list[datetime]] = {}
        self.values: list[object] = []
        self.cleared: list[str] = []
        self.lookups: list[str] = []

    async def consume_login_ip_attempt(self, digest: str, *, now: datetime):
        cutoff = now - timedelta(minutes=15)
        attempts = [value for value in self.ip_attempts.get(digest, []) if value > cutoff]
        self.ip_attempts[digest] = attempts
        if len(attempts) >= 20:
            retry = max(1, int((attempts[0] + timedelta(minutes=15) - now).total_seconds()))
            return LoginLimitDecision(False, retry)
        attempts.append(now)
        return LoginLimitDecision(True)

    async def lock_login_account_state(self, digest: str, *, now: datetime):
        state = self.account.get(digest)
        if state is not None and state.locked_until is not None and state.locked_until <= now:
            self.account.pop(digest)
            return None
        return state

    @staticmethod
    def account_retry_after(state, *, now: datetime):
        if state is None or state.locked_until is None or state.locked_until <= now:
            return None
        return max(1, int((state.locked_until - now).total_seconds()))

    async def record_login_failure(self, digest: str, *, state, now: datetime):
        if state is None:
            state = LoginAccountAbuseState(
                subject_digest=digest,
                consecutive_failures=0,
            )
            self.account[digest] = state
        state.consecutive_failures += 1
        state.last_failed_at = now
        if state.consecutive_failures >= 5:
            state.consecutive_failures = 5
            state.locked_until = now + timedelta(minutes=15)
            return 900
        return None

    async def clear_login_account_state(self, digest: str):
        self.account.pop(digest, None)
        self.cleared.append(digest)

    async def find_user_by_username(self, username: str):
        self.lookups.append(username)
        return self.user if self.user is not None and username == self.user.username else None

    async def set_authentication_user_scope(self, user_id):
        return None

    async def set_platform_scope(self):
        return None

    async def organizations(self, *, active_only=False):
        return []

    async def add(self, value):
        if value.id is None:
            value.id = uuid4()
        self.values.append(value)
        return value


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 5, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


def service(repository: AbuseRepository, hasher: SpyHasher, clock: Clock) -> SessionService:
    return SessionService(
        repository,
        password_hasher=hasher,
        access_token=FakeToken(),
        abuse_keys=LoginAbuseKeys(SecretStr("synthetic-login-abuse-secret-material")),
        now_provider=clock,
    )


@pytest.mark.asyncio
async def test_unknown_user_runs_dummy_verify_and_matches_wrong_password_response() -> None:
    clock = Clock()
    unknown_hasher = SpyHasher()
    unknown = service(AbuseRepository(None), unknown_hasher, clock)
    known_user = User(
        id=uuid4(),
        username="known",
        display_name="Known",
        password_hash="real-hash",
        status="active",
        platform_role="PLATFORM_ADMIN",
    )
    known_hasher = SpyHasher()
    known = service(AbuseRepository(known_user), known_hasher, clock)

    with pytest.raises(DomainError) as unknown_error:
        await unknown.login(username="missing", password="wrong", client_ip="192.0.2.1")
    with pytest.raises(DomainError) as known_error:
        await known.login(username="known", password="wrong", client_ip="192.0.2.2")

    assert (unknown_error.value.status_code, unknown_error.value.code) == (
        401,
        "invalid_credentials",
    )
    assert (known_error.value.status_code, known_error.value.code) == (
        401,
        "invalid_credentials",
    )
    assert len(unknown_hasher.calls) == len(known_hasher.calls) == 1
    assert unknown_hasher.calls[0][1].startswith("$argon2id$")
    assert len(unknown.repository.account) == len(known.repository.account) == 1


@pytest.mark.asyncio
async def test_abuse_normalization_does_not_rewrite_authentication_identity() -> None:
    clock = Clock()
    repository = AbuseRepository(None)
    login = service(repository, SpyHasher(), clock)
    submitted = "  ＳtaFF  "

    with pytest.raises(DomainError):
        await login.login(username=submitted, password="wrong", client_ip="192.0.2.8")

    assert repository.lookups == [submitted]


@pytest.mark.asyncio
async def test_login_abuse_path_does_not_log_raw_account_or_ip(caplog) -> None:
    clock = Clock()
    login = service(AbuseRepository(None), SpyHasher(), clock)
    account_sentinel = "raw-account-sentinel-013"
    password_sentinel = "raw-password-sentinel-013"
    ip_sentinel = "203.0.113.213"

    with pytest.raises(DomainError):
        await login.login(
            username=account_sentinel,
            password=password_sentinel,
            client_ip=ip_sentinel,
        )

    assert account_sentinel not in caplog.text
    assert password_sentinel not in caplog.text
    assert ip_sentinel not in caplog.text


@pytest.mark.asyncio
async def test_fifth_failure_locks_account_across_ips_and_correct_password() -> None:
    clock = Clock()
    user = User(
        id=uuid4(),
        username="staff",
        display_name="Staff",
        password_hash="real-hash",
        status="active",
        platform_role="PLATFORM_ADMIN",
    )
    repository = AbuseRepository(user)
    login = service(repository, SpyHasher(), clock)

    statuses = []
    for index in range(5):
        with pytest.raises(DomainError) as caught:
            await login.login(
                username="staff",
                password="wrong",
                client_ip=f"192.0.2.{index + 1}",
            )
        statuses.append(caught.value.status_code)
    assert statuses == [401, 401, 401, 401, 429]
    assert caught.value.headers == {"Retry-After": "900"}

    with pytest.raises(DomainError) as locked:
        await login.login(username="staff", password="correct", client_ip="192.0.2.99")
    assert locked.value.status_code == 429

    clock.value += timedelta(seconds=901)
    result = await login.login(username="staff", password="correct", client_ip="192.0.2.99")
    assert result["access_token"] == "access-token"
    assert repository.account == {}
    assert sum(len(values) for values in repository.ip_attempts.values()) == 6


@pytest.mark.asyncio
async def test_twenty_first_ip_attempt_is_429_and_success_does_not_clear_window() -> None:
    clock = Clock()
    user = User(
        id=uuid4(),
        username="admin",
        display_name="Admin",
        password_hash="real-hash",
        status="active",
        platform_role="PLATFORM_ADMIN",
    )
    repository = AbuseRepository(user)
    login = service(repository, SpyHasher(), clock)

    await login.login(username="admin", password="correct", client_ip="198.51.100.1")
    for index in range(19):
        with pytest.raises(DomainError):
            await login.login(
                username=f"unknown-{index}",
                password="wrong",
                client_ip="198.51.100.1",
            )
    with pytest.raises(DomainError) as limited:
        await login.login(username="admin", password="correct", client_ip="198.51.100.1")
    assert limited.value.status_code == 429
    assert limited.value.headers == {"Retry-After": "900"}
    assert len(next(iter(repository.ip_attempts.values()))) == 20


@pytest.mark.asyncio
async def test_combined_limit_uses_longer_safe_retry_after() -> None:
    clock = Clock()
    repository = AbuseRepository(None)
    keys = LoginAbuseKeys(SecretStr("synthetic-login-abuse-secret-material"))
    account_digest = keys.account_digest("missing")
    ip_digest = keys.ip_digest("198.51.100.20")
    repository.account[account_digest] = LoginAccountAbuseState(
        subject_digest=account_digest,
        consecutive_failures=5,
        locked_until=clock.value + timedelta(seconds=800),
    )
    repository.ip_attempts[ip_digest] = [clock.value - timedelta(seconds=800)] * 20
    login = service(repository, SpyHasher(), clock)

    with pytest.raises(DomainError) as limited:
        await login.login(
            username="missing",
            password="wrong",
            client_ip="198.51.100.20",
        )

    assert limited.value.status_code == 429
    assert limited.value.headers == {"Retry-After": "800"}
