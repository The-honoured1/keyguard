"""
KeyGuard — API key authentication, rate limiting, and abuse prevention
as a drop-in Python library.

Works with zero infrastructure (SQLite + in-memory rate limiting)
or full production setup (PostgreSQL + Redis).

Quick Start:
    from keyguard import KeyGuard, KeyGuardConfig, KeyGuardMiddleware

    config = KeyGuardConfig(secret_key="my-secret")
    kg = KeyGuard(config)
    app.add_middleware(KeyGuardMiddleware, kg_instance=kg, protected_path="/api")
"""
from .config import KeyGuardConfig
from .middleware import KeyGuardMiddleware
from .models import Base, Organization, APIKey, UsageLog
from .services.auth_service import AuthService
from .core import KeyGuard

__all__ = [
    "KeyGuard",
    "KeyGuardConfig",
    "KeyGuardMiddleware",
    "Base",
    "Organization",
    "APIKey",
    "UsageLog",
    "AuthService",
]

__version__ = "0.2.0"
