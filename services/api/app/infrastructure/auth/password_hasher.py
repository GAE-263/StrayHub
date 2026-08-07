from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, encoded_hash: str) -> bool:
        try:
            return self._hasher.verify(encoded_hash, password)
        except (InvalidHash, VerificationError, VerifyMismatchError):
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(encoded_hash)
        except InvalidHash:
            return True
