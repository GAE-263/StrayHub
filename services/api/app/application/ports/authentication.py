from collections.abc import Mapping
from typing import Protocol


class PasswordHasherPort(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, encoded_hash: str) -> bool: ...

    def needs_rehash(self, encoded_hash: str) -> bool: ...


class AccessTokenPort(Protocol):
    def issue(self, claims: Mapping[str, object]) -> str: ...

    def verify(self, token: str) -> Mapping[str, object]: ...


class LineIdentityVerifierPort(Protocol):
    async def verify(self, token: str) -> str: ...
