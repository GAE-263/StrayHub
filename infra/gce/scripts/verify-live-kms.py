#!/usr/bin/env python3
from __future__ import annotations

import argparse
import secrets
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.pii import EncryptedPii, PiiContext
from services.api.app.infrastructure.security.pii_cipher import (
    GoogleCloudKmsPiiCipher,
    configured_pii_cipher,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify live Cloud KMS PII access through ADC")
    parser.add_argument("--kms-key-name", required=True)
    arguments = parser.parse_args()

    cipher = configured_pii_cipher(
        app_env="production",
        provider="gcp-kms",
        local_key_base64=None,
        active_key_version="unused",
        allow_local_provider=False,
        kms_key_name=arguments.kms_key_name,
    )
    if not isinstance(cipher, GoogleCloudKmsPiiCipher):
        raise SystemExit("[Live KMS acceptance] FAIL: non-KMS provider selected")

    context = PiiContext(
        organization_id=UUID("00000000-0000-4000-8000-0000000000e2"),
        application_id=UUID("00000000-0000-4000-8000-0000000002e2"),
        field_name="e2_acceptance",
        schema_version="v1",
    )
    plaintext = "synthetic-e2-pii-acceptance"
    encrypted = cipher.encrypt(plaintext, context=context)
    if not encrypted.ciphertext or not encrypted.key_version.startswith(
        f"{arguments.kms_key_name}/cryptoKeyVersions/"
    ):
        raise SystemExit("[Live KMS acceptance] FAIL: invalid encrypt response")
    restored = cipher.decrypt(encrypted, context=context)
    if not secrets.compare_digest(restored, plaintext):
        raise SystemExit("[Live KMS acceptance] FAIL: round trip mismatch")

    corrupted = bytearray(encrypted.ciphertext)
    corrupted[-1] ^= 1
    malformed = EncryptedPii(
        ciphertext=bytes(corrupted),
        algorithm=encrypted.algorithm,
        key_version=encrypted.key_version,
    )
    try:
        cipher.decrypt(malformed, context=context)
    except DomainError as error:
        if error.code != "pii_ciphertext_invalid":
            raise SystemExit("[Live KMS acceptance] FAIL: unsafe failure classification") from None
    else:
        raise SystemExit("[Live KMS acceptance] FAIL: malformed ciphertext was accepted")

    print(
        "[Live KMS acceptance] PASS: ADC encrypt/decrypt round trip and malformed-ciphertext "
        "failure verified"
    )


if __name__ == "__main__":
    main()
