from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class PiiContext:
    organization_id: UUID
    application_id: UUID
    field_name: str
    schema_version: str

    def associated_data(self) -> bytes:
        return (
            f"strayhub-pii|{self.schema_version}|{self.organization_id}|"
            f"{self.application_id}|{self.field_name}"
        ).encode()


@dataclass(frozen=True)
class EncryptedPii:
    ciphertext: bytes
    algorithm: str
    key_version: str


class PiiCipherPort(Protocol):
    def encrypt(self, plaintext: str, *, context: PiiContext) -> EncryptedPii: ...

    def decrypt(self, value: EncryptedPii, *, context: PiiContext) -> str: ...


@dataclass(frozen=True)
class PiiRevealAuditEvent:
    organization_id: UUID
    application_id: UUID
    actor_user_id: UUID
    actor_role: str
    purpose_code: str
    request_id: UUID
    policy_version: str
    provided_fields: tuple[str, ...]
    encryption_key_version: str
    retention_expires_at: datetime


class PiiRevealAuditPort(Protocol):
    async def persist_committed_reveal(self, event: PiiRevealAuditEvent) -> None: ...
