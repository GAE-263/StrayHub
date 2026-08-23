from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from os import urandom
from types import MappingProxyType

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.pii import EncryptedPii, PiiContext
from services.api.app.config.settings import Settings


class AesGcmPiiCipher:
    algorithm = "AES-256-GCM"

    def __init__(self, *, keys: Mapping[str, bytes], active_key_version: str) -> None:
        copied_keys = dict(keys)
        if active_key_version not in copied_keys:
            raise ValueError("active PII key version is unavailable")
        if not copied_keys or any(len(key) != 32 for key in copied_keys.values()):
            raise ValueError("PII encryption keys must be 256-bit values")
        self._keys = MappingProxyType(copied_keys)
        self.active_key_version = active_key_version

    def encrypt(self, plaintext: str, *, context: PiiContext) -> EncryptedPii:
        nonce = urandom(12)
        ciphertext = AESGCM(self._keys[self.active_key_version]).encrypt(
            nonce,
            plaintext.encode("utf-8"),
            context.associated_data(),
        )
        return EncryptedPii(
            ciphertext=nonce + ciphertext,
            algorithm=self.algorithm,
            key_version=self.active_key_version,
        )

    def decrypt(self, value: EncryptedPii, *, context: PiiContext) -> str:
        key = self._keys.get(value.key_version)
        if key is None:
            raise DomainError("pii_key_unavailable", "個人資料暫時無法使用", 503)
        if value.algorithm != self.algorithm:
            raise DomainError("pii_ciphertext_invalid", "個人資料暫時無法使用", 503)
        nonce, ciphertext = value.ciphertext[:12], value.ciphertext[12:]
        try:
            plaintext = AESGCM(key).decrypt(
                nonce,
                ciphertext,
                context.associated_data(),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
            raise DomainError("pii_ciphertext_invalid", "個人資料暫時無法使用", 503) from exc


def configured_pii_cipher(
    *,
    app_env: str,
    provider: str,
    local_key_base64: str | None,
    active_key_version: str,
    allow_local_provider: bool = False,
) -> AesGcmPiiCipher:
    if (
        not allow_local_provider
        or app_env.lower() not in {"local", "test", "testing"}
        or provider != "local-aes-gcm"
    ):
        raise DomainError("pii_provider_unavailable", "個人資料加密服務尚未設定", 503)
    if not local_key_base64:
        raise DomainError("pii_provider_unavailable", "個人資料加密服務尚未設定", 503)
    try:
        key = base64.b64decode(local_key_base64, validate=True)
        return AesGcmPiiCipher(
            keys={active_key_version: key},
            active_key_version=active_key_version,
        )
    except (binascii.Error, ValueError) as exc:
        raise DomainError("pii_provider_unavailable", "個人資料加密服務尚未設定", 503) from exc


def configured_pii_cipher_from_settings(settings: Settings) -> AesGcmPiiCipher:
    key = settings.pii_local_key_base64
    return configured_pii_cipher(
        app_env=settings.app_env,
        provider=settings.pii_encryption_provider,
        local_key_base64=None if key is None else key.get_secret_value(),
        active_key_version=settings.pii_active_key_version,
        allow_local_provider=settings.pii_allow_local_provider,
    )
