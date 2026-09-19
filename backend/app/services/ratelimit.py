"""A tiny in-process sliding-window rate limiter.

Good enough for a single API instance. For multiple workers/instances, swap the
`_hits` dict for a shared store (Redis `INCR` with `EXPIRE`, or a token-bucket
Lua script) keyed the same way.
"""

import asyncio
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, times: int, window_seconds: float) -> None:
        self.times = times
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        async with self._lock:
            bucket = self._hits[key]
            cutoff = now - self.window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.times:
                retry_after = self.window - (now - bucket[0])
                return False, max(retry_after, 0.0)
            bucket.append(now)
            return True, 0.0
