"""
In-memory rate limiting service — no Redis required.

Uses a sliding window log algorithm backed by Python deques.
Suitable for single-process deployments and small projects.
"""
import asyncio
import time
from collections import defaultdict, deque
from typing import Tuple


class MemoryRateLimitService:
    """Drop-in replacement for RateLimitService that uses in-memory storage.

    Limitations vs Redis-backed:
    - State is lost on restart
    - Not shared across multiple processes/workers
    - For single-process / small project use only
    """

    def __init__(self):
        self._windows: dict[str, deque] = defaultdict(deque)
        self._abuse_counts: dict[str, tuple[int, float]] = {}  # ip -> (count, first_seen)
        self._blocked_ips: dict[str, float] = {}  # ip -> blocked_until
        self._lock = asyncio.Lock()

    async def is_rate_limited(
        self,
        key_id: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int]:
        """Check if a key has exceeded its rate limit.

        Returns: (is_limited, remaining_requests)
        """
        now = time.time()
        cutoff = now - window_seconds

        async with self._lock:
            window = self._windows[key_id]

            # Remove expired entries
            while window and window[0] <= cutoff:
                window.popleft()

            current_count = len(window)

            if current_count >= limit:
                return True, 0

            # Record this request
            window.append(now)
            remaining = limit - current_count - 1
            return False, max(0, remaining)

    async def is_ip_blocked(self, ip_address: str) -> bool:
        """Check if an IP is currently blocked."""
        async with self._lock:
            blocked_until = self._blocked_ips.get(ip_address)
            if blocked_until is None:
                return False
            if time.time() > blocked_until:
                # Block has expired
                del self._blocked_ips[ip_address]
                return False
            return True

    async def track_ip_abuse(self, ip_address: str, threshold: int = 100):
        """Track failed auth attempts per IP and block if threshold exceeded."""
        now = time.time()
        async with self._lock:
            count, first_seen = self._abuse_counts.get(ip_address, (0, now))

            # Reset if the tracking window (1 hour) has passed
            if now - first_seen > 3600:
                count = 0
                first_seen = now

            count += 1
            self._abuse_counts[ip_address] = (count, first_seen)

            if count > threshold:
                # Block for 24 hours
                self._blocked_ips[ip_address] = now + 86400

    async def cleanup(self):
        """Remove expired entries to prevent memory leaks.

        Call this periodically (e.g., every 5 minutes) in long-running apps.
        """
        now = time.time()
        async with self._lock:
            # Clean expired rate limit windows
            expired_keys = [
                k for k, v in self._windows.items()
                if not v or v[-1] < now - 120  # 2 minutes of inactivity
            ]
            for k in expired_keys:
                del self._windows[k]

            # Clean expired abuse counters
            expired_abuse = [
                ip for ip, (_, first_seen) in self._abuse_counts.items()
                if now - first_seen > 3600
            ]
            for ip in expired_abuse:
                del self._abuse_counts[ip]

            # Clean expired blocks
            expired_blocks = [
                ip for ip, until in self._blocked_ips.items()
                if now > until
            ]
            for ip in expired_blocks:
                del self._blocked_ips[ip]
