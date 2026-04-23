"""
KeyGuard — Zero-Infrastructure Example

This example works with just `pip install -e .` — no Docker, no Postgres, no Redis.
It uses SQLite for storage and in-memory rate limiting.

Run:
    pip install -e .
    python example_integration.py

Then test:
    # Public route (no key needed)
    curl http://localhost:8000/public

    # Protected route (needs a key — check terminal for the generated key)
    curl http://localhost:8000/api/data -H "X-API-KEY: <your-key>"

    # Admin: list keys
    curl http://localhost:8000/admin/keys -H "X-Admin-Key: my-secret"

    # Admin: view stats
    curl http://localhost:8000/admin/stats -H "X-Admin-Key: my-secret"
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends

from keyguard import KeyGuard, KeyGuardConfig, KeyGuardMiddleware, Organization, APIKey, rate_limit_by_ip
from keyguard.api.admin import create_admin_router


# ── 1. Configure (just a secret key!) ────────────────────────────
config = KeyGuardConfig(
    secret_key="my-secret",
    # That's it! SQLite + in-memory rate limiting by default.
    # For production, add:
    #   database_url="postgresql+asyncpg://user:pass@localhost/db",
    #   redis_url="redis://localhost:6379/0",
)

kg = KeyGuard(config)


# ── 2. App Setup with Lifespan ────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables and seed a test key
    await kg.init_db()
    await _seed_test_data()
    print("\n🚀 KeyGuard is running!")
    print("   Public:    http://localhost:8000/public")
    print("   Protected: http://localhost:8000/api/data")
    print("   Login (IP Limited): http://localhost:8000/login")
    print("   Admin:     http://localhost:8000/admin/keys")
    print("   Docs:      http://localhost:8000/docs\n")
    yield
    # Shutdown
    await kg.engine.dispose()


app = FastAPI(
    title="My Protected API",
    description="Example API protected by KeyGuard",
    version="1.0.0",
    lifespan=lifespan,
)


# ── 3. Add KeyGuard Middleware ────────────────────────────────────
# All routes under /api will require an X-API-KEY header
app.add_middleware(KeyGuardMiddleware, kg_instance=kg, protected_path="/api")


# ── 4. Mount Admin Router (optional) ─────────────────────────────
# Manage orgs and keys via HTTP — protected by X-Admin-Key header
app.include_router(
    create_admin_router(kg),
    prefix="/admin",
    tags=["KeyGuard Admin"],
)


# ── 5. Your Routes ───────────────────────────────────────────────

@app.get("/public")
async def public():
    """This route is NOT protected — anyone can access it."""
    return {"message": "This is public data. No API key needed."}


@app.post("/login")
async def login(_=Depends(rate_limit_by_ip(kg, limit=3, window=60, lockout=86400))):
    """
    Example login route with a 24-hour lockout.
    If you fail 3 times in a minute, you are blocked for 24 hours.
    """
    return {"message": "Login successful! (Allowed by IP rate limit)"}


@app.post("/signup")
async def signup(_=Depends(rate_limit_by_ip(kg, limit=2, window=3600, lockout="11:59 PM"))):
    """
    Example signup route with a lockout until 11:59 PM.
    If you hit the limit, you cannot try again until midnight.
    """
    return {"message": "Signup successful! (Allowed by strict IP rate limit)"}


@app.get("/api/data")
async def get_data(request: Request):
    """This route IS protected — requires a valid X-API-KEY header."""
    key = request.state.api_key
    return {
        "message": "You accessed protected data!",
        "your_key_label": key.label,
        "your_org": key.organization.name if key.organization else None,
        "scopes": key.scopes,
    }


@app.get("/api/profile")
async def get_profile(request: Request):
    """Another protected route — shows your key's information."""
    key = request.state.api_key
    return {
        "key_id": key.id,
        "org_id": key.org_id,
        "label": key.label,
        "rate_limit": key.rate_limit_per_minute,
        "scopes": key.scopes,
    }


# ── Seed Helper ──────────────────────────────────────────────────

async def _seed_test_data():
    """Creates a test org + key on first run (skips if data exists)."""
    from sqlalchemy import select

    async with kg.session_factory() as session:
        # Check if we already have data
        result = await session.execute(select(Organization))
        if result.scalar_one_or_none():
            return  # Already seeded

        # Create org
        org = Organization(name="Demo Org")
        session.add(org)
        await session.flush()

        # Create a key
        raw_key, key_hash = kg.auth.generate_api_key()
        api_key = APIKey(
            org_id=org.id,
            label="demo-key",
            prefix=raw_key[:12],
            key_hash=key_hash,
            rate_limit_per_minute=30,
            scopes=["read", "write"],
        )
        session.add(api_key)
        await session.commit()

        print(f"\n  ╔══════════════════════════════════════════════════════════╗")
        print(f"  ║  🔑 Demo API Key (use this in your requests)           ║")
        print(f"  ║                                                        ║")
        print(f"  ║  {raw_key:<54} ║")
        print(f"  ║                                                        ║")
        print(f"  ║  curl localhost:8000/api/data -H 'X-API-KEY: <key>'    ║")
        print(f"  ╚══════════════════════════════════════════════════════════╝\n")


# ── Run ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("example_integration:app", host="0.0.0.0", port=8000, reload=True)
