from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class PasswordHasherPort(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, encoded_hash: str) -> bool: ...

    def needs_rehash(self, encoded_hash: str) -> bool: ...


class AccessTokenPort(Protocol):
    def issue(self, claims: Mapping[str, object]) -> str: ...

    def verify(self, token: str) -> Mapping[str, object]: ...


class LineIdentityVerifierPort(Protocol):
    async def verify(self, token: str) -> str: ...


@dataclass(frozen=True)
class ActiveVolunteerEntryReference:
    reference_id: UUID
    organization_id: UUID
    organization_code: str
    organization_name: str


class VolunteerEntryResolverPort(Protocol):
    async def resolve(self, raw_reference: str) -> ActiveVolunteerEntryReference | None: ...
