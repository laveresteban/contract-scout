"""Sliding-window rate limiters.

Two interchangeable implementations behind one ``check(key) -> (allowed,
retry_after)`` contract:

* ``SlidingWindowLimiter`` — in-process, per-instance. Zero setup, but each
  worker counts on its own, so N workers allow N× the configured rate.
* ``RedisSlidingWindowLimiter`` — backs the same window on a shared Redis sorted
  set, so a limit is enforced *globally* across every worker/instance. Selected
  when ``CS_REDIS_URL`` is set (see ``build_limiter``).

Both keep the same semantics: at most ``times`` hits per ``window_seconds`` for a
given key, returning the seconds until the oldest in-window hit expires when a
call is refused.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict, deque
from typing import Protocol, runtime_checkable


@runtime_checkable
class RateLimiter(Protocol):
    times: int
    window: float

    async def check(self, key: str) -> tuple[bool, float]:
        ...


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


class RedisSlidingWindowLimiter:
    """Sliding window over a Redis sorted set of hit timestamps.

    One ZSET per key (member = unique id, score = wall-clock time). Each call
    trims expired members, counts what remains, and only adds itself when under
    the limit — so the count never overshoots and refused calls don't extend the
    window. Keys self-expire after ``window`` idle seconds so the store stays
    bounded without a sweeper.
    """

    _KEY_PREFIX = "cs:rl:"

    def __init__(self, redis, times: int, window_seconds: float) -> None:
        self._redis = redis
        self.times = times
        self.window = window_seconds

    async def check(self, key: str) -> tuple[bool, float]:
        redis_key = f"{self._KEY_PREFIX}{key}"
        now = time.time()
        cutoff = now - self.window
        await self._redis.zremrangebyscore(redis_key, 0, cutoff)
        count = await self._redis.zcard(redis_key)
        if count >= self.times:
            oldest = await self._redis.zrange(redis_key, 0, 0, withscores=True)
            retry_after = 0.0
            if oldest:
                retry_after = self.window - (now - float(oldest[0][1]))
            return False, max(retry_after, 0.0)
        await self._redis.zadd(redis_key, {f"{now}:{uuid.uuid4().hex}": now})
        # Expire slightly past the window so a fully-idle key is reclaimed.
        await self._redis.expire(redis_key, int(self.window) + 1)
        return True, 0.0


def build_limiter(settings) -> RateLimiter:
    """Pick the Redis-backed limiter when ``CS_REDIS_URL`` is set, else in-process.

    Redis is imported lazily so the dependency stays optional; if it's configured
    but the client can't be constructed, we log and fall back rather than fail to
    start.
    """
    import logging

    logger = logging.getLogger(__name__)
    times = settings.rate_limit_times
    window = settings.rate_limit_window_seconds
    url = getattr(settings, "redis_url", None)
    if url:
        try:
            from redis.asyncio import Redis

            client = Redis.from_url(url)
            logger.info("Rate limiting via Redis at %s (shared across workers)", url)
            return RedisSlidingWindowLimiter(client, times, window)
        except Exception:  # pragma: no cover - depends on env
            logger.exception("Redis rate limiter unavailable; using in-process limiter")
    return SlidingWindowLimiter(times, window)
