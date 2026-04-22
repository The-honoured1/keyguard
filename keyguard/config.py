from pydantic import BaseModel, ConfigDict
from typing import Optional

class KeyGuardConfig(BaseModel):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/keyguard"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "super-secret-admin-key-change-me"
    
    # Defaults
    default_rate_limit_per_minute: int = 60
    ip_block_threshold: int = 100
    
    # Advanced
    auto_init_db: bool = True

    model_config = ConfigDict(extra="ignore")
