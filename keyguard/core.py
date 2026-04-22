from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from .config import KeyGuardConfig
from .services.auth_service import AuthService
from .services.rate_limit_service import RateLimitService
from .models import Base

class KeyGuard:
    def __init__(self, config: KeyGuardConfig):
        self.config = config
        
        # Database setup
        self.engine = create_async_engine(
            config.database_url,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Services setup
        self.auth = AuthService(secret_key=config.secret_key)
        self.rate_limiting = RateLimitService(redis_url=config.redis_url)

    async def init_db(self):
        """Initializes KeyGuard tables in the host database."""
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
