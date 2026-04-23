from fastapi import Request, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
from datetime import datetime, time as dt_time, timedelta
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

        # 1. IP Blacklist Check (Global)
        if await self.kg.rate_limiting.is_blocked(ip_address):
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied. Your IP address is blocked."}
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


def rate_limit_by_ip(kg_instance, limit: int, window: int = 60, lockout: int | str = 0, scope: str = "path"):
    """FastAPI dependency factory for IP-based rate limiting.

    Useful for sensitive routes like login, signup, or heavy processing.
    Ensures that a single IP cannot brute-force or abuse specific endpoints.

    Args:
        kg_instance: KeyGuard instance.
        limit: Number of allowed requests.
        window: Sliding window in seconds.
        lockout: If set, blocks the IP when the limit is hit. Can be seconds (int)
                 or a specific time string (e.g., "4:00 PM").
        scope: "path" (default) to block only this route, or "global" to block the
               IP from all KeyGuard-protected routes.
    """
    async def dependency(request: Request):
        ip = request.client.host if request.client else "unknown"
        path_identifier = f"ip_limit:{ip}:{request.url.path}"

        # 1. Check if IP is already blocked GLOBALLY
        if await kg_instance.rate_limiting.is_blocked(ip):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Your IP address is blocked."
            )

        # 2. Check if this specific PATH is blocked (if using path scope)
        if scope == "path" and await kg_instance.rate_limiting.is_blocked(path_identifier):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this specific resource is temporarily blocked."
            )

        # 3. Check path-specific rate limit
        is_limited, remaining = await kg_instance.rate_limiting.is_rate_limited(
            key_id=path_identifier,
            limit=limit,
            window_seconds=window
        )

        if is_limited:
            # Trigger a lockout if configured
            if lockout:
                await kg_instance.block_request(request, lockout, scope=scope)

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


def seconds_until_time(target_time_str: str) -> int:
    """Calculates seconds until a specific time today or tomorrow."""
    now = datetime.now()
    try:
        # Support common formats: "16:00", "4:00 PM", "4 PM"
        t = None
        for fmt in ("%H:%M", "%I:%M %p", "%I %p"):
            try:
                t = datetime.strptime(target_time_str.strip(), fmt).time()
                break
            except ValueError:
                continue

        if not t:
            return 3600  # Fallback to 1 hour if unparseable

        target = datetime.combine(now.date(), t)
        if target <= now:
            # If the time has already passed today, target tomorrow
            target += timedelta(days=1)

        return int((target - now).total_seconds())
    except Exception:
        return 3600
