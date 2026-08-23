import base64
import traceback
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.ports.pii import EncryptedPii
from services.api.app.application.volunteer_pii_service import VolunteerPiiService
from services.api.app.config.settings import Settings
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.infrastructure.security.pii_cipher import (
    AesGcmPiiCipher,
    configured_pii_cipher,
    configured_pii_cipher_from_settings,
)
from services.api.app.persistence.models.identity import OrganizationMembership
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    VolunteerApplication,
)


def _insurance_policy(
    application: VolunteerApplication,
    *,
    required: bool = True,
) -> OrganizationVolunteerAccessPolicy:
    return OrganizationVolunteerAccessPolicy(
        organization_id=application.organization_id,
        insurance_required=required,
        version=3,
    )


class _ProfileCreateRepository:
    def __init__(
        self,
        application: VolunteerApplication,
        policy: OrganizationVolunteerAccessPolicy,
    ) -> None:
        self.application_value = application
        self.policy_value = policy
        self.added = None
        self.lock_calls: list[str] = []

    async def application(self, application_id, *, for_update=False):
        assert application_id == self.application_value.id
        assert for_update is True
        self.lock_calls.append("application")
        return self.application_value

    async def policy(self, *, for_update=False):
        assert for_update is True
        self.lock_calls.append("policy")
        return self.policy_value

    async def add(self, value):
        self.added = value
        return value


class _ProfileRevealRepository:
    def __init__(self, profile, *, role: str = "SHELTER_ADMIN") -> None:
        self.profile = profile
        self.organization_id = profile.organization_id
        self.role = role
        self.lock_calls: list[str] = []

    async def active_membership(self, user_id, *, for_update=False):
        assert for_update is True
        self.lock_calls.append("membership")
        return OrganizationMembership(
            organization_id=self.organization_id,
            user_id=user_id,
            role=self.role,
            status="active",
        )

    async def application_profile(self, application_id, *, for_update=False):
        assert application_id == self.profile.application_id
        assert for_update is True
        self.lock_calls.append("profile")
        return self.profile


def test_service_builds_encrypted_profile_without_plaintext_fields() -> None:
    organization_id = uuid4()
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=organization_id,
        user_id=uuid4(),
    )
    cipher = AesGcmPiiCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )
    service = VolunteerPiiService(cipher)
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)

    profile = service.build_profile(
        application=application,
        applicant_name="王小明",
        phone_number="0912345678",
        basic_profile={"experience": "新手"},
        insurance_identity=None,
        insurance_required=False,
        now=now,
    )

    assert profile.organization_id == organization_id
    assert profile.application_id == application.id
    assert profile.encryption_algorithm == "AES-256-GCM"
    assert profile.encryption_key_version == "local-v1"
    assert profile.applicant_name_ciphertext != "王小明".encode()
    assert profile.phone_ciphertext != b"0912345678"
    revealed = service._decrypt_profile(
        profile,
        organization_id=organization_id,
        application_id=application.id,
        now=now,
    )
    assert revealed.applicant_name == "王小明"
    assert revealed.phone_number == "0912345678"
    assert revealed.basic_profile == {"experience": "新手"}
    assert revealed.insurance_identity is None
    assert "王小明" not in repr(revealed)
    assert "0912345678" not in repr(revealed)
    assert "新手" not in repr(revealed)


def test_service_rejects_unknown_stored_pii_schema_version() -> None:
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    application = VolunteerApplication(id=uuid4(), organization_id=uuid4(), user_id=uuid4())
    service = VolunteerPiiService(
        AesGcmPiiCipher(keys={"local-v1": bytes(range(32))}, active_key_version="local-v1")
    )
    profile = service.build_profile(
        application=application,
        applicant_name="王小明",
        phone_number="0912345678",
        basic_profile=None,
        insurance_identity=None,
        insurance_required=False,
        now=now,
    )
    profile.pii_schema_version = "unknown-v2"

    with pytest.raises(DomainError) as error:
        service._decrypt_profile(
            profile,
            organization_id=application.organization_id,
            application_id=application.id,
            now=now,
        )

    assert error.value.code == "pii_schema_version_unknown"


def test_malformed_decrypted_basic_profile_never_leaks_through_exception() -> None:
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    application = VolunteerApplication(id=uuid4(), organization_id=uuid4(), user_id=uuid4())
    cipher = AesGcmPiiCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )
    service = VolunteerPiiService(cipher)
    profile = service.build_profile(
        application=application,
        applicant_name="王小明",
        phone_number="0912345678",
        basic_profile={"experience": "safe"},
        insurance_identity=None,
        insurance_required=False,
        now=now,
    )
    sentinel = "SENSITIVE_BASIC_PROFILE_NOT_JSON"
    malformed = cipher.encrypt(
        sentinel,
        context=service._context(profile, "basic_profile"),
    )
    profile.basic_profile_ciphertext = malformed.ciphertext

    with pytest.raises(DomainError) as error:
        service._decrypt_profile(
            profile,
            organization_id=application.organization_id,
            application_id=application.id,
            now=now,
        )

    formatted = "".join(traceback.format_exception(error.value))
    assert error.value.code == "pii_ciphertext_invalid"
    assert error.value.status_code == 503
    assert sentinel not in str(error.value)
    assert sentinel not in formatted


def test_service_rejects_inconsistent_field_encryption_metadata() -> None:
    class InconsistentCipher(AesGcmPiiCipher):
        encrypt_count = 0

        def encrypt(self, plaintext, *, context):
            encrypted = super().encrypt(plaintext, context=context)
            self.encrypt_count += 1
            if self.encrypt_count == 2:
                return EncryptedPii(
                    ciphertext=encrypted.ciphertext,
                    algorithm=encrypted.algorithm,
                    key_version="rotated-v2",
                )
            return encrypted

    application = VolunteerApplication(id=uuid4(), organization_id=uuid4(), user_id=uuid4())
    service = VolunteerPiiService(
        InconsistentCipher(keys={"local-v1": bytes(range(32))}, active_key_version="local-v1")
    )

    with pytest.raises(DomainError) as error:
        service.build_profile(
            application=application,
            applicant_name="王小明",
            phone_number="0912345678",
            basic_profile=None,
            insurance_identity=None,
            insurance_required=False,
            now=datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

    assert error.value.code == "pii_cipher_metadata_mismatch"


def test_service_does_not_force_raw_identity_when_insurer_can_collect_directly() -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    service = VolunteerPiiService(
        AesGcmPiiCipher(
            keys={"local-v1": bytes(range(32))},
            active_key_version="local-v1",
        )
    )

    profile = service.build_profile(
        application=application,
        applicant_name="王小明",
        phone_number="0912345678",
        basic_profile=None,
        insurance_identity=None,
        insurance_required=True,
        insurance_policy=_insurance_policy(application),
        insurance_collection_mode="insurer_direct",
        now=datetime(2026, 8, 23, tzinfo=timezone.utc),
    )

    assert profile.insurance_identity_ciphertext is None


def test_unscoped_builder_cannot_enable_raw_insurance_collection() -> None:
    application = VolunteerApplication(id=uuid4(), organization_id=uuid4(), user_id=uuid4())
    service = VolunteerPiiService(
        AesGcmPiiCipher(keys={"local-v1": bytes(range(32))}, active_key_version="local-v1")
    )

    with pytest.raises(DomainError) as error:
        service.build_profile(
            application=application,
            applicant_name="王小明",
            phone_number="0912345678",
            basic_profile=None,
            insurance_identity="A123456789",
            insurance_required=True,
            insurance_consent_acknowledged=True,
            insurance_policy=_insurance_policy(application),
            insurance_collection_mode="strayhub_temporary",
            insurance_purpose_code="insurance_verification",
            insurance_policy_version="organization-policy-v3",
            now=datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

    assert error.value.code == "insurance_identity_not_allowed"


@pytest.mark.asyncio
async def test_service_encrypts_required_insurance_identity_with_thirty_day_deadline() -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    service = VolunteerPiiService(
        AesGcmPiiCipher(
            keys={"local-v1": bytes(range(32))},
            active_key_version="local-v1",
        )
    )
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    sentinel_identity = "A123456789"

    repository = _ProfileCreateRepository(application, _insurance_policy(application))
    profile = await service.create_profile(
        repository=repository,  # type: ignore[arg-type]
        application_id=application.id,
        applicant_name="王小明",
        phone_number="0912345678",
        basic_profile=None,
        insurance_identity=sentinel_identity,
        insurance_consent_acknowledged=True,
        insurance_collection_mode="strayhub_temporary",
        insurance_purpose_code="insurance_verification",
        insurance_policy_version="organization-policy-v3",
        now=now,
    )

    assert profile.insurance_identity_ciphertext is not None
    assert repository.lock_calls == ["application", "policy"]
    assert repository.added is profile
    assert sentinel_identity.encode() not in profile.insurance_identity_ciphertext
    assert profile.insurance_identity_delete_after == now + timedelta(days=30)
    assert (
        service._decrypt_profile(
            profile,
            organization_id=application.organization_id,
            application_id=application.id,
            now=now,
            include_insurance=True,
        ).insurance_identity
        == sentinel_identity
    )


@pytest.mark.asyncio
async def test_service_rejects_insurance_identity_when_policy_does_not_require_it() -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    service = VolunteerPiiService(
        AesGcmPiiCipher(
            keys={"local-v1": bytes(range(32))},
            active_key_version="local-v1",
        )
    )

    repository = _ProfileCreateRepository(
        application,
        _insurance_policy(application, required=False),
    )
    with pytest.raises(DomainError) as error:
        await service.create_profile(
            repository=repository,  # type: ignore[arg-type]
            application_id=application.id,
            applicant_name="王小明",
            phone_number="0912345678",
            basic_profile=None,
            insurance_identity="A123456789",
            insurance_consent_acknowledged=True,
            insurance_collection_mode="strayhub_temporary",
            insurance_purpose_code="insurance_verification",
            insurance_policy_version="organization-policy-v3",
            now=datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

    assert error.value.code == "insurance_identity_not_allowed"
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_service_rejects_insurance_identity_without_separate_consent() -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    service = VolunteerPiiService(
        AesGcmPiiCipher(
            keys={"local-v1": bytes(range(32))},
            active_key_version="local-v1",
        )
    )

    repository = _ProfileCreateRepository(application, _insurance_policy(application))
    with pytest.raises(DomainError) as error:
        await service.create_profile(
            repository=repository,  # type: ignore[arg-type]
            application_id=application.id,
            applicant_name="王小明",
            phone_number="0912345678",
            basic_profile=None,
            insurance_identity="A123456789",
            insurance_consent_acknowledged=False,
            insurance_collection_mode="strayhub_temporary",
            insurance_purpose_code="insurance_verification",
            insurance_policy_version="organization-policy-v3",
            now=datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

    assert error.value.code == "insurance_consent_required"
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "basic_profile",
    [
        {"national_id": "A123456789"},
        {"insurance_identity": "A123456789"},
        {"experience": {"identity": "A123456789"}},
    ],
)
def test_service_rejects_unknown_or_nested_basic_profile_fields(basic_profile: dict) -> None:
    application = VolunteerApplication(id=uuid4(), organization_id=uuid4(), user_id=uuid4())
    service = VolunteerPiiService(
        AesGcmPiiCipher(keys={"local-v1": bytes(range(32))}, active_key_version="local-v1")
    )

    with pytest.raises(DomainError) as error:
        service.build_profile(
            application=application,
            applicant_name="王小明",
            phone_number="0912345678",
            basic_profile=basic_profile,
            insurance_identity=None,
            insurance_required=False,
            now=datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

    assert error.value.code == "basic_profile_invalid"
    assert error.value.status_code == 422


def test_production_rejects_plaintext_runtime_master_key_fallback() -> None:
    raw_key = base64.b64encode(bytes(range(32))).decode()

    with pytest.raises(DomainError) as error:
        configured_pii_cipher(
            app_env="production",
            provider="local-aes-gcm",
            local_key_base64=raw_key,
            active_key_version="production-v1",
        )

    assert error.value.code == "pii_provider_unavailable"
    assert error.value.status_code == 503
    assert raw_key not in str(error.value)


@pytest.mark.parametrize("app_env", ["staging", "production-eu", "unknown"])
def test_non_local_environment_rejects_local_master_key_fallback(app_env: str) -> None:
    with pytest.raises(DomainError) as error:
        configured_pii_cipher(
            app_env=app_env,
            provider="local-aes-gcm",
            local_key_base64=base64.b64encode(bytes(range(32))).decode(),
            active_key_version="unsafe-v1",
        )

    assert error.value.code == "pii_provider_unavailable"


def test_pii_settings_do_not_embed_a_default_encryption_key() -> None:
    settings = Settings(_env_file=None)

    assert settings.pii_encryption_provider == "local-aes-gcm"
    assert settings.pii_active_key_version == "local-v1"
    assert settings.pii_local_key_base64 is None
    assert settings.pii_allow_local_provider is False


def test_local_cipher_requires_explicit_provider_opt_in() -> None:
    with pytest.raises(DomainError) as error:
        configured_pii_cipher(
            app_env="local",
            provider="local-aes-gcm",
            local_key_base64=base64.b64encode(bytes(range(32))).decode(),
            active_key_version="local-v1",
        )

    assert error.value.code == "pii_provider_unavailable"


def test_local_cipher_reads_one_time_key_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        pii_allow_local_provider=True,
        pii_local_key_base64=base64.b64encode(bytes(range(32))).decode(),
        pii_active_key_version="test-v1",
    )

    cipher = configured_pii_cipher_from_settings(settings)

    assert cipher.active_key_version == "test-v1"


@pytest.mark.asyncio
async def test_retention_purge_removes_insurance_identity_at_thirty_days_only() -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    service = VolunteerPiiService(
        AesGcmPiiCipher(
            keys={"local-v1": bytes(range(32))},
            active_key_version="local-v1",
        )
    )
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    repository = _ProfileCreateRepository(application, _insurance_policy(application))
    profile = await service.create_profile(
        repository=repository,  # type: ignore[arg-type]
        application_id=application.id,
        applicant_name="王小明",
        phone_number="0912345678",
        basic_profile=None,
        insurance_identity="A123456789",
        insurance_consent_acknowledged=True,
        insurance_collection_mode="strayhub_temporary",
        insurance_purpose_code="insurance_verification",
        insurance_policy_version="organization-policy-v3",
        now=now,
    )

    changed = service.purge_expired(profile, now=now + timedelta(days=30))

    assert changed is True
    assert profile.insurance_identity_ciphertext is None
    assert profile.insurance_identity_delete_after is None
    assert profile.applicant_name_ciphertext is not None
    assert (
        service._decrypt_profile(
            profile,
            organization_id=application.organization_id,
            application_id=application.id,
            now=now + timedelta(days=30),
            include_insurance=True,
        ).insurance_identity
        is None
    )


def test_retention_purge_tombstones_all_pii_at_general_deadline_idempotently() -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    service = VolunteerPiiService(
        AesGcmPiiCipher(
            keys={"local-v1": bytes(range(32))},
            active_key_version="local-v1",
        )
    )
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    profile = service.build_profile(
        application=application,
        applicant_name="王小明",
        phone_number="0912345678",
        basic_profile={"experience": "新手"},
        insurance_identity=None,
        insurance_required=False,
        now=now,
    )
    deadline = now + timedelta(days=180)

    assert service.purge_expired(profile, now=deadline) is True
    assert profile.pii_deleted_at == deadline
    assert profile.applicant_name_ciphertext is None
    assert profile.phone_ciphertext is None
    assert profile.basic_profile_ciphertext is None
    assert profile.insurance_identity_ciphertext is None
    assert service.purge_expired(profile, now=deadline + timedelta(days=1)) is False
    assert profile.pii_deleted_at == deadline
    with pytest.raises(DomainError) as error:
        service._decrypt_profile(
            profile,
            organization_id=application.organization_id,
            application_id=application.id,
            now=deadline,
        )
    assert error.value.code == "pii_deleted"
    assert error.value.status_code == 410


def test_service_rejects_profile_moved_to_another_expected_binding_before_decrypt() -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    service = VolunteerPiiService(
        AesGcmPiiCipher(
            keys={"local-v1": bytes(range(32))},
            active_key_version="local-v1",
        )
    )
    sentinel_name = "王小明"
    profile = service.build_profile(
        application=application,
        applicant_name=sentinel_name,
        phone_number="0912345678",
        basic_profile=None,
        insurance_identity=None,
        insurance_required=False,
        now=datetime(2026, 8, 23, tzinfo=timezone.utc),
    )

    with pytest.raises(DomainError) as error:
        service._decrypt_profile(
            profile,
            organization_id=uuid4(),
            application_id=application.id,
            now=datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

    assert error.value.code == "pii_profile_not_found"
    assert error.value.status_code == 404
    assert sentinel_name not in str(error.value)


@pytest.mark.asyncio
async def test_reveal_does_not_decrypt_when_durable_audit_fails() -> None:
    class SpyCipher(AesGcmPiiCipher):
        decrypt_called = False

        def decrypt(self, value, *, context):
            self.decrypt_called = True
            return super().decrypt(value, context=context)

    class FailingAudit:
        async def persist_committed_reveal(self, event) -> None:
            raise RuntimeError("audit commit failed")

    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    cipher = SpyCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )
    service = VolunteerPiiService(cipher)
    sentinel_name = "測試志工甲"
    profile = service.build_profile(
        application=application,
        applicant_name=sentinel_name,
        phone_number="0900000001",
        basic_profile=None,
        insurance_identity=None,
        insurance_required=False,
        now=datetime(2026, 8, 23, tzinfo=timezone.utc),
    )

    with pytest.raises(DomainError) as error:
        await service.reveal_profile(
            repository=_ProfileRevealRepository(profile),  # type: ignore[arg-type]
            application_id=application.id,
            tenant_context=TenantContext(
                user_id=uuid4(),
                organization_id=application.organization_id,
                role="SHELTER_ADMIN",
            ),
            purpose_code="application_review",
            request_id=uuid4(),
            policy_version="volunteer-pii-v1",
            now=datetime(2026, 8, 24, tzinfo=timezone.utc),
            audit=FailingAudit(),
        )

    assert cipher.decrypt_called is False
    assert error.value.code == "pii_audit_unavailable"
    assert error.value.status_code == 503
    assert "audit commit failed" not in str(error.value)
    assert sentinel_name not in str(error.value)


@pytest.mark.asyncio
async def test_reveal_persists_allowlisted_audit_metadata_before_decrypt() -> None:
    sequence: list[str] = []

    class SpyCipher(AesGcmPiiCipher):
        def decrypt(self, value, *, context):
            sequence.append("decrypt")
            return super().decrypt(value, context=context)

    class CaptureAudit:
        event = None

        async def persist_committed_reveal(self, event) -> None:
            sequence.append("audit")
            self.event = event

    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    service = VolunteerPiiService(
        SpyCipher(
            keys={"local-v1": bytes(range(32))},
            active_key_version="local-v1",
        )
    )
    sentinel_name = "測試志工乙"
    sentinel_phone = "0900000002"
    profile = service.build_profile(
        application=application,
        applicant_name=sentinel_name,
        phone_number=sentinel_phone,
        basic_profile=None,
        insurance_identity=None,
        insurance_required=False,
        now=datetime(2026, 8, 23, tzinfo=timezone.utc),
    )
    audit = CaptureAudit()
    reveal_repository = _ProfileRevealRepository(profile)

    revealed = await service.reveal_profile(
        repository=reveal_repository,  # type: ignore[arg-type]
        application_id=application.id,
        tenant_context=TenantContext(
            user_id=uuid4(),
            organization_id=application.organization_id,
            role="SHELTER_ADMIN",
        ),
        purpose_code="application_review",
        request_id=uuid4(),
        policy_version="volunteer-pii-v1",
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        audit=audit,
    )

    assert sequence[0] == "audit"
    assert reveal_repository.lock_calls == ["membership", "profile"]
    assert sequence[1:] == ["decrypt", "decrypt"]
    assert audit.event.provided_fields == ("applicant_name", "phone_number")
    assert sentinel_name not in repr(audit.event)
    assert sentinel_phone not in repr(audit.event)
    assert revealed.applicant_name == sentinel_name


@pytest.mark.asyncio
async def test_reveal_rejects_expired_profile_before_audit_or_decrypt() -> None:
    class AuditMustNotRun:
        called = False

        async def persist_committed_reveal(self, event) -> None:
            self.called = True

    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    application = VolunteerApplication(id=uuid4(), organization_id=uuid4(), user_id=uuid4())
    service = VolunteerPiiService(
        AesGcmPiiCipher(keys={"local-v1": bytes(range(32))}, active_key_version="local-v1")
    )
    profile = service.build_profile(
        application=application,
        applicant_name="測試志工丁",
        phone_number="0900000004",
        basic_profile=None,
        insurance_identity=None,
        insurance_required=False,
        now=now,
    )
    audit = AuditMustNotRun()

    with pytest.raises(DomainError) as error:
        await service.reveal_profile(
            repository=_ProfileRevealRepository(profile),  # type: ignore[arg-type]
            application_id=application.id,
            tenant_context=TenantContext(
                user_id=uuid4(),
                organization_id=application.organization_id,
                role="SHELTER_ADMIN",
            ),
            purpose_code="application_review",
            request_id=uuid4(),
            policy_version="volunteer-pii-v1",
            now=profile.retention_expires_at,
            audit=audit,
        )

    assert error.value.code == "pii_expired"
    assert audit.called is False


@pytest.mark.asyncio
async def test_reveal_rejects_non_allowlisted_role_before_audit() -> None:
    class AuditMustNotRun:
        called = False

        async def persist_committed_reveal(self, event) -> None:
            self.called = True

    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    application = VolunteerApplication(id=uuid4(), organization_id=uuid4(), user_id=uuid4())
    service = VolunteerPiiService(
        AesGcmPiiCipher(keys={"local-v1": bytes(range(32))}, active_key_version="local-v1")
    )
    profile = service.build_profile(
        application=application,
        applicant_name="測試志工戊",
        phone_number="0900000005",
        basic_profile=None,
        insurance_identity=None,
        insurance_required=False,
        now=now,
    )
    audit = AuditMustNotRun()
    staff_repository = _ProfileRevealRepository(profile, role="STAFF")

    with pytest.raises(DomainError) as error:
        await service.reveal_profile(
            repository=staff_repository,  # type: ignore[arg-type]
            application_id=application.id,
            tenant_context=TenantContext(
                user_id=uuid4(),
                organization_id=application.organization_id,
                role="SHELTER_ADMIN",
            ),
            purpose_code="application_review",
            request_id=uuid4(),
            policy_version="volunteer-pii-v1",
            now=now,
            audit=audit,
        )

    assert error.value.code == "pii_reveal_forbidden"
    assert audit.called is False

    with pytest.raises(DomainError) as platform_error:
        await service.reveal_profile(
            repository=_ProfileRevealRepository(profile),  # type: ignore[arg-type]
            application_id=application.id,
            tenant_context=TenantContext(
                user_id=uuid4(),
                organization_id=None,
                role="SHELTER_ADMIN",
                platform_scope=True,
            ),
            purpose_code="application_review",
            request_id=uuid4(),
            policy_version="volunteer-pii-v1",
            now=now,
            audit=audit,
        )

    assert platform_error.value.code == "pii_profile_not_found"
    assert audit.called is False


@pytest.mark.asyncio
async def test_crm_reveal_never_returns_insurance_identity() -> None:
    class CaptureAudit:
        event = None

        async def persist_committed_reveal(self, event) -> None:
            self.event = event

    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    application = VolunteerApplication(id=uuid4(), organization_id=uuid4(), user_id=uuid4())
    service = VolunteerPiiService(
        AesGcmPiiCipher(keys={"local-v1": bytes(range(32))}, active_key_version="local-v1")
    )
    repository = _ProfileCreateRepository(application, _insurance_policy(application))
    profile = await service.create_profile(
        repository=repository,  # type: ignore[arg-type]
        application_id=application.id,
        applicant_name="測試志工己",
        phone_number="0900000006",
        basic_profile=None,
        insurance_identity="Z999999999",
        insurance_consent_acknowledged=True,
        insurance_collection_mode="strayhub_temporary",
        insurance_purpose_code="insurance_verification",
        insurance_policy_version="organization-policy-v3",
        now=now,
    )
    audit = CaptureAudit()
    reveal_repository = _ProfileRevealRepository(profile)

    revealed = await service.reveal_profile(
        repository=reveal_repository,  # type: ignore[arg-type]
        application_id=application.id,
        tenant_context=TenantContext(
            user_id=uuid4(),
            organization_id=application.organization_id,
            role="SHELTER_ADMIN",
        ),
        purpose_code="application_review",
        request_id=uuid4(),
        policy_version="volunteer-pii-v1",
        now=now,
        audit=audit,
    )

    assert reveal_repository.lock_calls == ["membership", "profile"]
    assert revealed.insurance_identity is None
    assert "insurance_identity" not in audit.event.provided_fields
    assert "Z999999999" not in repr(revealed)
