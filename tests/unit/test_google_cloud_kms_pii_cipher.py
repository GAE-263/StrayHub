from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from services.api.app.api.errors import DomainError
from services.api.app.application.ports.pii import EncryptedPii, PiiContext
from services.api.app.application.volunteer_pii_service import VolunteerPiiService
from services.api.app.config.settings import Settings
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.infrastructure.security.pii_cipher import (
    GoogleCloudKmsPiiCipher,
    configured_pii_cipher_from_settings,
)
from services.api.app.persistence.models.volunteer_access import VolunteerApplication


class _FakeKmsClient:
    def __init__(self, key_name: str) -> None:
        self.key_name = key_name
        self.active_version = "1"
        self.keys = {
            "1": bytes(range(32)),
            "2": bytes(reversed(range(32))),
        }
        self.decrypt_calls = 0
        self.events: list[str] = []
        self.fail_encrypt = False
        self.fail_decrypt = False

    def encrypt(self, *, request):
        if self.fail_encrypt:
            raise RuntimeError("synthetic KMS unavailable")
        assert request["name"] == self.key_name
        version = self.active_version
        nonce = bytes([int(version)]) * 12
        ciphertext = AESGCM(self.keys[version]).encrypt(
            nonce,
            request["plaintext"],
            request["additional_authenticated_data"],
        )
        return SimpleNamespace(
            ciphertext=version.encode() + b":" + nonce + ciphertext,
            name=f"{self.key_name}/cryptoKeyVersions/{version}",
        )

    def decrypt(self, *, request):
        if self.fail_decrypt:
            raise RuntimeError("synthetic KMS unavailable")
        assert request["name"] == self.key_name
        self.decrypt_calls += 1
        self.events.append("decrypt")
        version, ciphertext = request["ciphertext"].split(b":", 1)
        nonce, payload = ciphertext[:12], ciphertext[12:]
        return SimpleNamespace(
            plaintext=AESGCM(self.keys[version.decode()]).decrypt(
                nonce,
                payload,
                request["additional_authenticated_data"],
            )
        )


class _PermissionDeniedKmsClient:
    def encrypt(self, *, request):
        raise PermissionError("synthetic KMS permission denied")

    def decrypt(self, *, request):
        raise PermissionError("synthetic KMS permission denied")


@pytest.fixture
def kms_key_name() -> str:
    return "projects/test-project/locations/asia-east1/keyRings/pii/cryptoKeys/volunteer"


@pytest.fixture
def context() -> PiiContext:
    return PiiContext(
        organization_id=uuid4(),
        application_id=uuid4(),
        field_name="applicant_name",
        schema_version="v1",
    )


def test_gcp_environment_selects_kms_provider_when_configured(kms_key_name: str) -> None:
    client = _FakeKmsClient(kms_key_name)
    settings = Settings(
        _env_file=None,
        app_env="gcp-demo",
        pii_encryption_provider="gcp-kms",
        pii_kms_key_name=kms_key_name,
    )

    cipher = configured_pii_cipher_from_settings(
        settings,
        kms_client_factory=lambda: client,
    )

    assert isinstance(cipher, GoogleCloudKmsPiiCipher)


def test_gcp_environment_without_kms_configuration_fails_closed() -> None:
    settings = Settings(
        _env_file=None,
        app_env="gcp-demo",
        pii_encryption_provider="gcp-kms",
    )

    with pytest.raises(DomainError) as error:
        configured_pii_cipher_from_settings(settings, kms_client_factory=lambda: object())

    assert error.value.code == "pii_provider_unavailable"
    assert error.value.status_code == 503


def test_gcp_environment_rejects_invalid_kms_key_reference() -> None:
    settings = Settings(
        _env_file=None,
        app_env="gcp-demo",
        pii_encryption_provider="gcp-kms",
        pii_kms_key_name="projects/test/locations/asia-east1/keyRings/pii/cryptoKeys/key/extra",
    )

    with pytest.raises(DomainError) as error:
        configured_pii_cipher_from_settings(settings, kms_client_factory=lambda: object())

    assert error.value.code == "pii_provider_unavailable"
    assert error.value.status_code == 503


def test_kms_cipher_round_trip_preserves_provider_key_version(
    kms_key_name: str, context: PiiContext
) -> None:
    cipher = GoogleCloudKmsPiiCipher(kms_key_name, _FakeKmsClient(kms_key_name))

    encrypted = cipher.encrypt("Synthetic Applicant", context=context)

    assert encrypted.algorithm == "GOOGLE-CLOUD-KMS"
    assert encrypted.key_version == f"{kms_key_name}/cryptoKeyVersions/1"
    assert encrypted.ciphertext != b"Synthetic Applicant"
    assert cipher.decrypt(encrypted, context=context) == "Synthetic Applicant"


@pytest.mark.parametrize("changed_binding", ["organization", "application", "field"])
def test_kms_cipher_rejects_wrong_context(
    kms_key_name: str, context: PiiContext, changed_binding: str
) -> None:
    cipher = GoogleCloudKmsPiiCipher(kms_key_name, _FakeKmsClient(kms_key_name))
    encrypted = cipher.encrypt("Synthetic Applicant", context=context)
    wrong_context = PiiContext(
        organization_id=uuid4() if changed_binding == "organization" else context.organization_id,
        application_id=uuid4() if changed_binding == "application" else context.application_id,
        field_name="phone_number" if changed_binding == "field" else context.field_name,
        schema_version=context.schema_version,
    )

    with pytest.raises(DomainError) as error:
        cipher.decrypt(encrypted, context=wrong_context)

    assert error.value.code == "pii_ciphertext_invalid"
    assert error.value.status_code == 503
    assert "Synthetic Applicant" not in str(error.value)


def test_kms_cipher_rejects_key_version_from_another_key(
    kms_key_name: str, context: PiiContext
) -> None:
    client = _FakeKmsClient(kms_key_name)
    cipher = GoogleCloudKmsPiiCipher(kms_key_name, client)
    encrypted = cipher.encrypt("Synthetic Applicant", context=context)
    foreign = EncryptedPii(
        ciphertext=encrypted.ciphertext,
        algorithm=encrypted.algorithm,
        key_version=(
            "projects/other/locations/asia-east1/keyRings/pii/cryptoKeys/volunteer/"
            "cryptoKeyVersions/1"
        ),
    )

    with pytest.raises(DomainError) as error:
        cipher.decrypt(foreign, context=context)

    assert error.value.code == "pii_key_unavailable"
    assert client.decrypt_calls == 0


def test_kms_cipher_supports_old_version_after_rotation(
    kms_key_name: str, context: PiiContext
) -> None:
    client = _FakeKmsClient(kms_key_name)
    cipher = GoogleCloudKmsPiiCipher(kms_key_name, client)
    encrypted = cipher.encrypt("Synthetic Applicant", context=context)
    client.active_version = "2"

    assert cipher.decrypt(encrypted, context=context) == "Synthetic Applicant"
    assert encrypted.key_version.endswith("/cryptoKeyVersions/1")


def test_kms_provider_failures_are_safe_and_never_fall_back(
    kms_key_name: str, context: PiiContext
) -> None:
    client = _FakeKmsClient(kms_key_name)
    cipher = GoogleCloudKmsPiiCipher(kms_key_name, client)
    client.fail_encrypt = True

    with pytest.raises(DomainError) as encrypt_error:
        cipher.encrypt("Synthetic Applicant", context=context)

    assert encrypt_error.value.code == "pii_provider_unavailable"
    assert "Synthetic Applicant" not in str(encrypt_error.value)


def test_kms_permission_denied_fails_closed_without_plaintext(
    kms_key_name: str, context: PiiContext
) -> None:
    cipher = GoogleCloudKmsPiiCipher(kms_key_name, _PermissionDeniedKmsClient())

    with pytest.raises(DomainError) as error:
        cipher.encrypt("Synthetic Applicant", context=context)

    assert error.value.code == "pii_provider_unavailable"
    assert error.value.status_code == 503
    assert "Synthetic Applicant" not in str(error.value)


def test_kms_decrypt_failure_is_safe(kms_key_name: str, context: PiiContext) -> None:
    client = _FakeKmsClient(kms_key_name)
    cipher = GoogleCloudKmsPiiCipher(kms_key_name, client)
    encrypted = cipher.encrypt("Synthetic Applicant", context=context)
    client.fail_decrypt = True

    with pytest.raises(DomainError) as error:
        cipher.decrypt(encrypted, context=context)

    assert error.value.status_code == 503
    assert "Synthetic Applicant" not in str(error.value)


def test_kms_permission_denied_on_decrypt_fails_closed(
    kms_key_name: str, context: PiiContext
) -> None:
    encrypted = GoogleCloudKmsPiiCipher(kms_key_name, _FakeKmsClient(kms_key_name)).encrypt(
        "Synthetic Applicant", context=context
    )
    cipher = GoogleCloudKmsPiiCipher(kms_key_name, _PermissionDeniedKmsClient())

    with pytest.raises(DomainError) as error:
        cipher.decrypt(encrypted, context=context)

    assert error.value.code == "pii_ciphertext_invalid"
    assert error.value.status_code == 503
    assert "Synthetic Applicant" not in str(error.value)


def test_kms_malformed_ciphertext_fails_closed(kms_key_name: str, context: PiiContext) -> None:
    malformed = EncryptedPii(
        ciphertext=b"synthetic-malformed-ciphertext",
        algorithm=GoogleCloudKmsPiiCipher.algorithm,
        key_version=f"{kms_key_name}/cryptoKeyVersions/1",
    )
    cipher = GoogleCloudKmsPiiCipher(kms_key_name, _FakeKmsClient(kms_key_name))

    with pytest.raises(DomainError) as error:
        cipher.decrypt(malformed, context=context)

    assert error.value.code == "pii_ciphertext_invalid"
    assert error.value.status_code == 503
    assert "synthetic-malformed-ciphertext" not in str(error.value)


class _ProfileRepository:
    def __init__(self, application: VolunteerApplication) -> None:
        self.organization_id = application.organization_id
        self.application_value = application
        self.profile = None
        self.session = object()

    async def application(self, application_id, *, for_update=False):
        assert application_id == self.application_value.id
        assert for_update is True
        return self.application_value

    async def policy(self, *, for_update=False):
        assert for_update is True
        return SimpleNamespace(insurance_required=False, version=7)

    async def add(self, profile):
        self.profile = profile
        return profile

    async def active_membership(self, user_id, *, for_update=False):
        assert for_update is True
        return SimpleNamespace(
            organization_id=self.organization_id,
            user_id=user_id,
            role="SHELTER_ADMIN",
            status="active",
        )

    async def application_profile(self, application_id, *, for_update=False):
        assert application_id == self.application_value.id
        assert for_update is True
        return self.profile


class _CaptureRevealAudit:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.event = None

    async def persist_committed_reveal(self, event) -> None:
        self.events.append("audit")
        self.event = event


class _FailingRevealAudit:
    async def persist_committed_reveal(self, event) -> None:
        raise RuntimeError("synthetic audit persistence failure")


def test_volunteer_pii_service_round_trip_uses_kms_cipher(kms_key_name: str) -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    service = VolunteerPiiService(
        GoogleCloudKmsPiiCipher(kms_key_name, _FakeKmsClient(kms_key_name))
    )
    profile = service.build_profile(
        application=application,
        applicant_name="Synthetic Applicant",
        phone_number="0900000000",
        basic_profile={"experience": "synthetic"},
        insurance_identity=None,
        insurance_required=False,
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )

    revealed = service._decrypt_profile(
        profile,
        organization_id=application.organization_id,
        application_id=application.id,
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )

    assert profile.encryption_algorithm == "GOOGLE-CLOUD-KMS"
    assert profile.encryption_key_version.endswith("/cryptoKeyVersions/1")
    assert len(profile.encryption_key_version) > 80
    assert revealed.applicant_name == "Synthetic Applicant"
    assert "Synthetic Applicant" not in repr(revealed)


@pytest.mark.asyncio
async def test_volunteer_pii_service_audits_before_kms_reveal(kms_key_name: str) -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    client = _FakeKmsClient(kms_key_name)
    repository = _ProfileRepository(application)
    service = VolunteerPiiService(GoogleCloudKmsPiiCipher(kms_key_name, client))
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    profile = await service.create_profile(
        repository=repository,  # type: ignore[arg-type]
        application_id=application.id,
        applicant_name="Synthetic Applicant",
        phone_number="0900000000",
        basic_profile={"experience": "synthetic"},
        insurance_identity=None,
        insurance_consent_acknowledged=False,
        insurance_collection_mode=None,
        insurance_purpose_code=None,
        insurance_policy_version=None,
        now=now,
    )
    assert profile.applicant_name_ciphertext != b"Synthetic Applicant"

    audit = _CaptureRevealAudit(client.events)
    revealed = await service.reveal_profile(
        repository=repository,  # type: ignore[arg-type]
        application_id=application.id,
        tenant_context=TenantContext(
            user_id=uuid4(),
            organization_id=application.organization_id,
            role="SHELTER_ADMIN",
        ),
        purpose_code="application_review",
        request_id=uuid4(),
        policy_version="organization-policy-v7",
        now=now,
        audit=audit,
    )

    assert audit.event is not None
    assert client.events.index("audit") < client.events.index("decrypt")
    assert revealed.applicant_name == "Synthetic Applicant"
    assert "Synthetic Applicant" not in repr(audit.event)


@pytest.mark.asyncio
async def test_kms_reveal_does_not_decrypt_when_audit_fails(kms_key_name: str) -> None:
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
    )
    client = _FakeKmsClient(kms_key_name)
    repository = _ProfileRepository(application)
    service = VolunteerPiiService(GoogleCloudKmsPiiCipher(kms_key_name, client))
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    await service.create_profile(
        repository=repository,  # type: ignore[arg-type]
        application_id=application.id,
        applicant_name="Synthetic Applicant",
        phone_number="0900000000",
        basic_profile=None,
        insurance_identity=None,
        insurance_consent_acknowledged=False,
        insurance_collection_mode=None,
        insurance_purpose_code=None,
        insurance_policy_version=None,
        now=now,
    )

    with pytest.raises(DomainError) as error:
        await service.reveal_profile(
            repository=repository,  # type: ignore[arg-type]
            application_id=application.id,
            tenant_context=TenantContext(
                user_id=uuid4(),
                organization_id=application.organization_id,
                role="SHELTER_ADMIN",
            ),
            purpose_code="application_review",
            request_id=uuid4(),
            policy_version="organization-policy-v7",
            now=now,
            audit=_FailingRevealAudit(),
        )

    assert error.value.code == "pii_audit_unavailable"
    assert "Synthetic Applicant" not in str(error.value)
    assert client.decrypt_calls == 0
