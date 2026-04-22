import asyncio
from fastapi import FastAPI, Depends
from keyguard import KeyGuard, KeyGuardConfig, KeyGuardMiddleware
from sqlalchemy import select
from uuid import uuid4

# 1. Initialize KeyGuard Configuration
config = KeyGuardConfig(
    database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/keyguard",
    redis_url="redis://localhost:6379/0",
    secret_key="my-super-secret-key"
)

# 2. Setup KeyGuard Core
kg = KeyGuard(config)

# 3. Setup FastAPI
app = FastAPI(title="My Protected API")

# 4. Add the KeyGuard Middleware
# This will protect all routes starting with /api
app.add_middleware(KeyGuardMiddleware, kg_instance=kg, protected_path="/api")

@app.on_event("startup")
async def startup():
    # Initialize KeyGuard tables
    await kg.init_db()
    print("KeyGuard initialized!")

@app.get("/api/data")
async def get_data():
    return {"message": "You accessed protected data!"}

@app.get("/public")
async def public():
    return {"message": "This is public info."}

# Helper to create a test key programmatically
async def setup_test_data():
    from keyguard.models import Organization, APIKey
    async with kg.session_factory() as session:
        # Create Org
        org = Organization(name="Test Org")
        session.add(org)
        await session.flush()
        
        # Create Key
        raw_key, key_hash = kg.auth.generate_api_key()
        api_key = APIKey(
            org_id=org.id,
            label="My Test Key",
            prefix=raw_key[:8],
            key_hash=key_hash,
            rate_limit_per_minute=10
        )
        session.add(api_key)
        await session.commit()
        
        print(f"--- TEST DATA CREATED ---")
        print(f"API KEY: {raw_key}")
        print(f"-------------------------")

if __name__ == "__main__":
    import uvicorn
    # To run this, you'd usually run: uvicorn example_integration:app --reload
    # We use this block to run the setup helper then the app
    async def main():
        # Optional: Setup some data first
        # await setup_test_data()
        config = uvicorn.Config(app, host="0.0.0.0", port=8000)
        server = uvicorn.Server(config)
        await server.serve()
        
    asyncio.run(main())
