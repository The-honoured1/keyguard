import time
from typing import Optional, Tuple
import redis.asyncio as redis
from app.core.config import settings

class RateLimitService:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    async def is_rate_limited(
        self, 
        key_id: str, 
        limit: int, 
        window_seconds: int = 60
    ) -> Tuple[bool, int]:
        """
        Sliding Window Log algorithm using Redis ZSET.
        Returns: (is_limited, remaining_calls)
        """
        now = time.time()
        # Redis key format: ratelimit:{key_hash}
        redis_key = f"ratelimit:{key_id}"
        
        # Calculate the window boundary
        cutoff = now - window_seconds
        
        async with self.redis.pipeline(transaction=True) as pipe:
            # 1. Remove old timestamps
            pipe.zremrangebyscore(redis_key, 0, cutoff)
            # 2. Count requests in the current window
            pipe.zcard(redis_key)
            # 3. Add current timestamp (will be conditional in logic)
            pipe.zadd(redis_key, {str(now): now})
            # 4. Set TTL to clean up stagnant sets
            pipe.expire(redis_key, window_seconds + 1)
            
            results = await pipe.execute()
            
            current_count = results[1]
            
            if current_count >= limit:
                # If we exceed the limit, we should ideally remove the timestamp we just added
                # to prevent a "burst" of failed requests from clogging the window,
                # but "Sliding Window Log" usually counts all attempts.
                # For efficiency, we'll just check the count.
                return True, 0
            
            remaining = limit - current_count - 1
            return False, max(0, remaining)

    async def is_ip_blocked(self, ip_address: str) -> bool:
        """
        Checks if an IP is in the blacklist.
        """
        blocked = await self.redis.get(f"block:{ip_address}")
        return blocked is not None

    async def track_ip_abuse(self, ip_address: str, threshold: int = 100):
        """
        Simple IP throttling logic: if an IP fails auth too many times.
        """
        key = f"abuse:{ip_address}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 3600)  # 1 hour window
        
        if count > threshold:
            await self.redis.set(f"block:{ip_address}", "1", ex=86400) # Block for 24h

# Global instance for easy access
rate_limit_service = RateLimitService(settings.REDIS_URL)
