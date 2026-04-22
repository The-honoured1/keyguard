from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "KeyGuard API Gateway"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/keyguard"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "super-secret-admin-key-change-me"
    ALGORITHM: str = "HS256"
    
    # KeyGuard Defaults
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 60
    IP_BLOCK_THRESHOLD: int = 100

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
