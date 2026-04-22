from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.db.base import AsyncSessionLocal
from app.db.models import APIKey, Organization, UsageLog
from app.services.auth_service import auth_service
from app.services.rate_limit_service import rate_limit_service
from app.core.logging import logger
from app.core.config import settings

class KeyGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Skip middleware for admin stats or health checks if needed
        # For simplicity, we only apply to /api/v1/gateway routes
        if not request.url.path.startswith(f"{settings.API_V1_STR}/gateway"):
            return await call_next(request)

        start_time = time.time()
        ip_address = request.client.host

        # 2. IP Blacklist Check
        if await rate_limit_service.is_ip_blocked(ip_address):
            return JSONResponse(
                status_code=403,
                content={"detail": "IP address blocked due to abuse."}
            )

        # 3. Extract API Key
        api_key_raw = request.headers.get("X-API-KEY")
        if not api_key_raw:
            await rate_limit_service.track_ip_abuse(ip_address)
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API Key."}
            )

        # 4. Auth & Rate Limit Check
        key_hash = auth_service.hash_key(api_key_raw)
        
        async with AsyncSessionLocal() as session:
            # Query for the key and organization status
            result = await session.execute(
                select(APIKey)
                .options(selectinload(APIKey.organization))
                .where(APIKey.key_hash == key_hash, APIKey.is_active == True)
            )
            key_obj = result.scalar_one_or_none()

            if not key_obj or key_obj.organization.status != "active":
                await rate_limit_service.track_ip_abuse(ip_address)
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or inactive API Key."}
                )

            # 5. Rate Limiting
            is_limited, remaining = await rate_limit_service.is_rate_limited(
                key_id=key_hash, 
                limit=key_obj.rate_limit_per_minute
            )
            
            if is_limited:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded."},
                    headers={"X-RateLimit-Limit": str(key_obj.rate_limit_per_minute), "X-RateLimit-Remaining": "0"}
                )

            # 6. Proceed with Request
            # Attach key info to request state for the route handler
            request.state.api_key = key_obj
            response = await call_next(request)

            # 7. Post-Request: Logging & Usage Tracking (Background)
            latency = int((time.time() - start_time) * 1000)
            
            # Update last used timestamp
            key_obj.last_used_at = func.now() if hasattr(key_obj, 'last_used_at') else None # func.now() needs sqlalchemy.sql
            
            # Log usage (in a real system, move this to a task queue)
            usage = UsageLog(
                key_id=key_obj.id,
                path=request.url.path,
                method=request.method,
                status_code=response.status_code,
                latency_ms=latency,
                ip_address=ip_address
            )
            session.add(usage)
            await session.commit()

            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(key_obj.rate_limit_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            
            return response
