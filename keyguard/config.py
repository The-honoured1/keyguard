from pydantic import BaseModel, ConfigDict
from typing import Optional


class KeyGuardConfig(BaseModel):
    """Configuration for KeyGuard.

    For small projects, only `secret_key` is truly required.
    Everything else has sensible defaults that work with zero infrastructure.
    """

    # Database — defaults to a local SQLite file (no server needed)
    database_url: str = "sqlite+aiosqlite:///keyguard.db"

    # Redis — optional. When None, uses in-memory rate limiting.
    redis_url: Optional[str] = None

    # Security — pepper used when hashing API keys
    secret_key: str = "super-secret-admin-key-change-me"

    # Defaults
    default_rate_limit_per_minute: int = 60
    ip_block_threshold: int = 100

    # Advanced
    auto_init_db: bool = True

    model_config = ConfigDict(extra="ignore")

    @property
    def is_sqlite(self) -> bool:
        """Check if the configured database is SQLite."""
        return self.database_url.startswith("sqlite")

    @property
    def is_redis_enabled(self) -> bool:
        """Check if Redis is configured."""
        return self.redis_url is not None
