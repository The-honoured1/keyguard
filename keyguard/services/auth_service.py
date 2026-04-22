import secrets
import hashlib
from typing import Tuple
from app.core.config import settings

class AuthService:
    @staticmethod
    def generate_api_key(prefix: str = "kg_live_") -> Tuple[str, str]:
        """
        Generates a new API key and its hash.
        Returns: (raw_key, hashed_key)
        """
        # Generate 32 bytes of secure random data
        random_part = secrets.token_urlsafe(32)
        raw_key = f"{prefix}{random_part}"
        
        # Hash the key for storage
        # In a real system, we'd add a pepper from settings
        key_hash = AuthService.hash_key(raw_key)
        
        return raw_key, key_hash

    @staticmethod
    def hash_key(key: str) -> str:
        """
        Hashes the key using SHA-256 with a secret pepper.
        """
        payload = f"{key}{settings.SECRET_KEY}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def verify_key(provided_key: str, stored_hash: str) -> bool:
        """
        Verifies a provided key against a stored hash.
        """
        return AuthService.hash_key(provided_key) == stored_hash

auth_service = AuthService()
