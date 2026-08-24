from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.infrastructure.security.pii_cipher import (
    AesGcmPiiCipher,
    EncryptedPii,
    PiiContext,
)


def test_aes_gcm_encrypts_plaintext_with_versioned_application_field_context() -> None:
    organization_id = uuid4()
    application_id = uuid4()
    context = PiiContext(
        organization_id=organization_id,
        application_id=application_id,
        field_name="applicant_name",
        schema_version="v1",
    )
    plaintext = "王小明"
    cipher = AesGcmPiiCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )

    encrypted = cipher.encrypt(plaintext, context=context)

    assert encrypted.algorithm == "AES-256-GCM"
    assert encrypted.key_version == "local-v1"
    assert plaintext.encode() not in encrypted.ciphertext
    assert cipher.decrypt(encrypted, context=context) == plaintext


def test_aes_gcm_rejects_ciphertext_moved_to_another_tenant_context() -> None:
    original_context = PiiContext(
        organization_id=uuid4(),
        application_id=uuid4(),
        field_name="phone",
        schema_version="v1",
    )
    wrong_tenant_context = PiiContext(
        organization_id=uuid4(),
        application_id=original_context.application_id,
        field_name="phone",
        schema_version="v1",
    )
    cipher = AesGcmPiiCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )
    sentinel_phone = "0912345678"
    encrypted = cipher.encrypt(sentinel_phone, context=original_context)

    with pytest.raises(DomainError) as error:
        cipher.decrypt(encrypted, context=wrong_tenant_context)

    assert error.value.code == "pii_ciphertext_invalid"
    assert error.value.status_code == 503
    assert sentinel_phone not in str(error.value)


def test_aes_gcm_rejects_unknown_key_version_with_safe_error() -> None:
    context = PiiContext(
        organization_id=uuid4(),
        application_id=uuid4(),
        field_name="applicant_name",
        schema_version="v1",
    )
    cipher = AesGcmPiiCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )
    value = EncryptedPii(
        ciphertext=b"0" * 32,
        algorithm="AES-256-GCM",
        key_version="missing-sensitive-version",
    )

    with pytest.raises(DomainError) as error:
        cipher.decrypt(value, context=context)

    assert error.value.code == "pii_key_unavailable"
    assert error.value.status_code == 503
    assert value.key_version not in str(error.value)


@pytest.mark.parametrize("changed_binding", ["application", "field"])
def test_aes_gcm_rejects_wrong_application_or_field_binding(changed_binding: str) -> None:
    context = PiiContext(
        organization_id=uuid4(),
        application_id=uuid4(),
        field_name="phone_number",
        schema_version="v1",
    )
    wrong_context = PiiContext(
        organization_id=context.organization_id,
        application_id=uuid4() if changed_binding == "application" else context.application_id,
        field_name="applicant_name" if changed_binding == "field" else context.field_name,
        schema_version=context.schema_version,
    )
    cipher = AesGcmPiiCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )
    encrypted = cipher.encrypt("0912345678", context=context)

    with pytest.raises(DomainError) as error:
        cipher.decrypt(encrypted, context=wrong_context)

    assert error.value.code == "pii_ciphertext_invalid"


def test_aes_gcm_rejects_tampered_ciphertext() -> None:
    context = PiiContext(
        organization_id=uuid4(),
        application_id=uuid4(),
        field_name="applicant_name",
        schema_version="v1",
    )
    cipher = AesGcmPiiCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )
    encrypted = cipher.encrypt("王小明", context=context)
    tampered = EncryptedPii(
        ciphertext=encrypted.ciphertext[:-1] + bytes([encrypted.ciphertext[-1] ^ 1]),
        algorithm=encrypted.algorithm,
        key_version=encrypted.key_version,
    )

    with pytest.raises(DomainError) as error:
        cipher.decrypt(tampered, context=context)

    assert error.value.code == "pii_ciphertext_invalid"


def test_aes_gcm_rejects_mismatched_algorithm_metadata() -> None:
    context = PiiContext(
        organization_id=uuid4(),
        application_id=uuid4(),
        field_name="applicant_name",
        schema_version="v1",
    )
    cipher = AesGcmPiiCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )
    encrypted = cipher.encrypt("王小明", context=context)
    wrong_algorithm = EncryptedPii(
        ciphertext=encrypted.ciphertext,
        algorithm="AES-128-GCM",
        key_version=encrypted.key_version,
    )

    with pytest.raises(DomainError) as error:
        cipher.decrypt(wrong_algorithm, context=context)

    assert error.value.code == "pii_ciphertext_invalid"


def test_aes_gcm_rejects_malformed_short_payload_with_safe_error() -> None:
    context = PiiContext(
        organization_id=uuid4(),
        application_id=uuid4(),
        field_name="phone_number",
        schema_version="v1",
    )
    cipher = AesGcmPiiCipher(
        keys={"local-v1": bytes(range(32))},
        active_key_version="local-v1",
    )
    malformed = EncryptedPii(
        ciphertext=b"x",
        algorithm="AES-256-GCM",
        key_version="local-v1",
    )

    with pytest.raises(DomainError) as error:
        cipher.decrypt(malformed, context=context)

    assert error.value.code == "pii_ciphertext_invalid"
    assert error.value.status_code == 503
