from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, gateway
from app.middleware.gateway import KeyGuardMiddleware
from app.core.config import settings
from app.core.logging import logger

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

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.VERSION}

    @app.on_event("startup")
    async def startup_event():
        logger.info("Initializing KeyGuard...")

    return app

app = create_app()
