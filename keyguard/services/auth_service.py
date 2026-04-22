import secrets
import hashlib
from typing import Tuple

class AuthService:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def generate_api_key(self, prefix: str = "kg_live_") -> Tuple[str, str]:
        """
        Generates a new API key and its hash.
        Returns: (raw_key, hashed_key)
        """
        random_part = secrets.token_urlsafe(32)
        raw_key = f"{prefix}{random_part}"
        key_hash = self.hash_key(raw_key)
        return raw_key, key_hash

    def hash_key(self, key: str) -> str:
        """
        Hashes the key using SHA-256 with a secret pepper.
        """
        payload = f"{key}{self.secret_key}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def verify_key(self, provided_key: str, stored_hash: str) -> bool:
        """
        Verifies a provided key against a stored hash.
        """
        return self.hash_key(provided_key) == stored_hash
