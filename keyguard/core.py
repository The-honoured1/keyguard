from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from .config import KeyGuardConfig
from .services.auth_service import AuthService
from .models import Base


class KeyGuard:
    """Core KeyGuard instance.

    Manages database connections, authentication, and rate limiting.
    Automatically selects the right backend based on your config:

    - SQLite or PostgreSQL for storage
    - Redis or in-memory for rate limiting

    Usage:
        config = KeyGuardConfig(secret_key="my-secret")
        kg = KeyGuard(config)
        await kg.init_db()
    """

    def __init__(self, config: KeyGuardConfig):
        self.config = config

        # Database setup — adapt engine args for SQLite vs Postgres
        engine_kwargs = {}
        if config.is_sqlite:
            # SQLite doesn't support pool_pre_ping or connection pooling the same way
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["pool_pre_ping"] = True

        self.engine = create_async_engine(
            config.database_url,
            **engine_kwargs,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Auth service
        self.auth = AuthService(secret_key=config.secret_key)

        # Rate limiting — Redis or in-memory
        if config.is_redis_enabled:
            from .services.rate_limit_service import RateLimitService
            self.rate_limiting = RateLimitService(redis_url=config.redis_url)
        else:
            from .services.memory_rate_limit import MemoryRateLimitService
            self.rate_limiting = MemoryRateLimitService()

    async def init_db(self):
        """Creates all KeyGuard tables in the configured database.

        Safe to call multiple times — only creates tables that don't exist.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_db(self):
        """Async generator for database sessions."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
