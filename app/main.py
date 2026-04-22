from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.v1 import admin, gateway
from app.middleware.gateway import KeyGuardMiddleware
from app.core.config import settings
from app.core.logging import logger
from app.db.base import engine
from app.db.models import Base

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    # Standard CORS support
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # KeyGuard Core Logic Middleware
    app.add_middleware(KeyGuardMiddleware)

    # Include Routers
    app.include_router(admin.router, prefix=f"{settings.API_V1_STR}/admin", tags=["Admin"])
    app.include_router(gateway.router, prefix=f"{settings.API_V1_STR}/gateway", tags=["Gateway"])

    # Serve Frontend
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse("frontend/index.html")

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.VERSION}

    @app.on_event("startup")
    async def startup_event():
        logger.info("Initializing KeyGuard...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized.")

    return app

app = create_app()
