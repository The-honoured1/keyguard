import time
from typing import Tuple
import redis.asyncio as redis

class RateLimitService:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    async def is_rate_limited(
        self, 
        key_id: str, 
        limit: int, 
        window_seconds: int = 60
    ) -> Tuple[bool, int]:
        now = time.time()
        redis_key = f"ratelimit:{key_id}"
        cutoff = now - window_seconds
        
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, cutoff)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {str(now): now})
            pipe.expire(redis_key, window_seconds + 1)
            
            results = await pipe.execute()
            current_count = results[1]
            
            if current_count >= limit:
                return True, 0
            
            remaining = limit - current_count - 1
            return False, max(0, remaining)

    async def is_ip_blocked(self, ip_address: str) -> bool:
        blocked = await self.redis.get(f"block:{ip_address}")
        return blocked is not None

    async def block_ip(self, ip_address: str, duration_seconds: int):
        """Manually block an IP for a specific duration."""
        await self.redis.set(f"block:{ip_address}", "1", ex=duration_seconds)

    async def track_ip_abuse(self, ip_address: str, threshold: int = 100):
        key = f"abuse:{ip_address}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 3600)
        
        if count > threshold:
            await self.redis.set(f"block:{ip_address}", "1", ex=86400)
