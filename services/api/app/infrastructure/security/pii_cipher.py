from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Mapping
from os import urandom
from types import MappingProxyType
from typing import Any, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.pii import EncryptedPii, PiiContext
from services.api.app.config.settings import Settings, is_kms_crypto_key_name


class GoogleCloudKmsClient(Protocol):
    def encrypt(self, *, request: dict[str, Any]) -> Any: ...

    def decrypt(self, *, request: dict[str, Any]) -> Any: ...


GoogleCloudKmsClientFactory = Callable[[], GoogleCloudKmsClient]


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


class GoogleCloudKmsPiiCipher:
    """Cloud KMS-backed PII cipher with field-scoped authenticated data."""

    algorithm = "GOOGLE-CLOUD-KMS"

    def __init__(self, key_name: str, client: GoogleCloudKmsClient) -> None:
        normalized_key_name = key_name.strip()
        if not is_kms_crypto_key_name(normalized_key_name):
            raise DomainError("pii_provider_unavailable", "個人資料加密服務尚未設定", 503)
        self.key_name = normalized_key_name
        self.client = client
        self._version_prefix = f"{self.key_name}/cryptoKeyVersions/"

    def _valid_key_version(self, key_version: str) -> bool:
        return (
            key_version.startswith(self._version_prefix)
            and len(key_version) > len(self._version_prefix)
            and "/" not in key_version[len(self._version_prefix) :]
        )

    def encrypt(self, plaintext: str, *, context: PiiContext) -> EncryptedPii:
        try:
            response = self.client.encrypt(
                request={
                    "name": self.key_name,
                    "plaintext": plaintext.encode("utf-8"),
                    "additional_authenticated_data": context.associated_data(),
                }
            )
            ciphertext = response.ciphertext
            key_version = response.name
            if not isinstance(ciphertext, bytes) or not isinstance(key_version, str):
                raise ValueError
            if not ciphertext or not self._valid_key_version(key_version):
                raise ValueError
        except Exception:
            raise DomainError("pii_provider_unavailable", "個人資料加密服務尚未設定", 503) from None
        return EncryptedPii(
            ciphertext=ciphertext,
            algorithm=self.algorithm,
            key_version=key_version,
        )

    def decrypt(self, value: EncryptedPii, *, context: PiiContext) -> str:
        if value.algorithm != self.algorithm:
            raise DomainError("pii_ciphertext_invalid", "個人資料暫時無法使用", 503)
        if not self._valid_key_version(value.key_version):
            raise DomainError("pii_key_unavailable", "個人資料暫時無法使用", 503)
        try:
            response = self.client.decrypt(
                request={
                    "name": self.key_name,
                    "ciphertext": value.ciphertext,
                    "additional_authenticated_data": context.associated_data(),
                }
            )
            plaintext = response.plaintext
            if not isinstance(plaintext, bytes):
                raise ValueError
            return plaintext.decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            raise DomainError("pii_ciphertext_invalid", "個人資料暫時無法使用", 503) from None
        except Exception:
            raise DomainError("pii_ciphertext_invalid", "個人資料暫時無法使用", 503) from None


def _google_cloud_kms_client() -> GoogleCloudKmsClient:
    try:
        from google.cloud import kms_v1

        return kms_v1.KeyManagementServiceClient()
    except Exception:
        raise DomainError("pii_provider_unavailable", "個人資料加密服務尚未設定", 503) from None


def configured_pii_cipher(
    *,
    app_env: str,
    provider: str,
    local_key_base64: str | None,
    active_key_version: str,
    allow_local_provider: bool = False,
    kms_key_name: str | None = None,
    kms_client_factory: GoogleCloudKmsClientFactory | None = None,
) -> AesGcmPiiCipher | GoogleCloudKmsPiiCipher:
    normalized_provider = provider.strip()
    if normalized_provider == "local-aes-gcm":
        if not allow_local_provider or app_env.lower() not in {"local", "test", "testing"}:
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
    if normalized_provider == "gcp-kms" and kms_key_name:
        factory = kms_client_factory or _google_cloud_kms_client
        try:
            return GoogleCloudKmsPiiCipher(kms_key_name, factory())
        except DomainError:
            raise
        except Exception:
            raise DomainError("pii_provider_unavailable", "個人資料加密服務尚未設定", 503) from None
    raise DomainError("pii_provider_unavailable", "個人資料加密服務尚未設定", 503)


def configured_pii_cipher_from_settings(
    settings: Settings,
    *,
    kms_client_factory: GoogleCloudKmsClientFactory | None = None,
) -> AesGcmPiiCipher | GoogleCloudKmsPiiCipher:
    key = settings.pii_local_key_base64
    return configured_pii_cipher(
        app_env=settings.app_env,
        provider=settings.pii_encryption_provider,
        local_key_base64=None if key is None else key.get_secret_value(),
        active_key_version=settings.pii_active_key_version,
        allow_local_provider=settings.pii_allow_local_provider,
        kms_key_name=settings.pii_kms_key_name,
        kms_client_factory=kms_client_factory,
    )
