from fastapi import Request, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .models import APIKey, UsageLog


class KeyGuardMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that protects routes with API key authentication.

    Attaches the validated API key object to `request.state.api_key`
    for use in downstream route handlers.
    """

    def __init__(self, app, kg_instance, protected_path: str = "/api"):
        super().__init__(app)
        self.kg = kg_instance
        self.protected_path = protected_path

    async def dispatch(self, request: Request, call_next):
        # Only protect specific paths
        if not request.url.path.startswith(self.protected_path):
            return await call_next(request)

        start_time = time.time()
        ip_address = request.client.host if request.client else "unknown"

        # 1. IP Blacklist Check
        if await self.kg.rate_limiting.is_ip_blocked(ip_address):
            return JSONResponse(
                status_code=403,
                content={"detail": "IP address blocked due to abuse."}
            )

        # 2. Extract API Key
        api_key_raw = request.headers.get("X-API-KEY")
        if not api_key_raw:
            await self.kg.rate_limiting.track_ip_abuse(
                ip_address, threshold=self.kg.config.ip_block_threshold
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API Key. Include X-API-KEY header."}
            )

        # 3. Auth & Rate Limit Check
        key_hash = self.kg.auth.hash_key(api_key_raw)

        async with self.kg.session_factory() as session:
            result = await session.execute(
                select(APIKey)
                .options(selectinload(APIKey.organization))
                .where(APIKey.key_hash == key_hash, APIKey.is_active == True)
            )
            key_obj = result.scalar_one_or_none()

            if not key_obj or key_obj.organization.status != "active":
                await self.kg.rate_limiting.track_ip_abuse(
                    ip_address, threshold=self.kg.config.ip_block_threshold
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or inactive API Key."}
                )

            # 4. Rate Limiting
            is_limited, remaining = await self.kg.rate_limiting.is_rate_limited(
                key_id=key_hash,
                limit=key_obj.rate_limit_per_minute
            )

            if is_limited:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded."},
                    headers={
                        "X-RateLimit-Limit": str(key_obj.rate_limit_per_minute),
                        "X-RateLimit-Remaining": "0"
                    }
                )

            # 5. Successfully authenticated
            request.state.api_key = key_obj
            response = await call_next(request)

            # 6. Post-Request: Logging
            latency = int((time.time() - start_time) * 1000)

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


def rate_limit_by_ip(kg_instance, limit: int, window: int = 60):
    """FastAPI dependency factory for IP-based rate limiting.

    Useful for login, signup, and other routes that don't use API keys.
    Ensures that a single IP cannot brute-force authentication endpoints.

    Usage:
        @app.post("/login", dependencies=[Depends(rate_limit_by_ip(kg, limit=5))])
        async def login():
            ...
    """
    async def dependency(request: Request):
        ip = request.client.host if request.client else "unknown"

        # 1. Check if IP is already blocked (global block)
        if await kg_instance.rate_limiting.is_ip_blocked(ip):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="IP address blocked due to abuse."
            )

        # 2. Check path-specific rate limit
        # We prefix with 'ip_limit' and include the path to avoid collisions
        is_limited, remaining = await kg_instance.rate_limiting.is_rate_limited(
            key_id=f"ip_limit:{ip}:{request.url.path}",
            limit=limit,
            window_seconds=window
        )

        if is_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0"
                }
            )

        return True

    return dependency
