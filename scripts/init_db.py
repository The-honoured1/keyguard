import asyncio
from app.db.base import engine
from app.db.models import Base

async def init_models():
    async with engine.begin() as conn:
        # NOTE: This will drop tables if they exist in some contexts, 
        # so use with caution in production.
        # But for an MVP/Example, this is the quickest way to get started.
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        print("Done.")

if __name__ == "__main__":
    asyncio.run(init_models())
