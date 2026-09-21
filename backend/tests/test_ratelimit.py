"""Rate limiters: the in-process sliding window and the Redis-backed one that
shares a limit across workers. The Redis tests run against fakeredis, so no
server is required."""

import fakeredis.aioredis
import pytest

from app.services.ratelimit import RedisSlidingWindowLimiter, SlidingWindowLimiter


async def test_in_process_allows_then_blocks():
    limiter = SlidingWindowLimiter(times=2, window_seconds=60)
    assert (await limiter.check("k"))[0] is True
    assert (await limiter.check("k"))[0] is True
    allowed, retry_after = await limiter.check("k")
    assert allowed is False and retry_after > 0


async def test_redis_allows_then_blocks():
    client = fakeredis.aioredis.FakeRedis()
    limiter = RedisSlidingWindowLimiter(client, times=2, window_seconds=60)
    assert (await limiter.check("k"))[0] is True
    assert (await limiter.check("k"))[0] is True
    allowed, retry_after = await limiter.check("k")
    assert allowed is False and retry_after > 0
    await client.aclose()


async def test_redis_limit_is_shared_across_instances():
    # Two limiters on one store == two workers behind one Redis: the limit is global.
    client = fakeredis.aioredis.FakeRedis()
    a = RedisSlidingWindowLimiter(client, times=3, window_seconds=60)
    b = RedisSlidingWindowLimiter(client, times=3, window_seconds=60)
    assert (await a.check("ip:1"))[0] is True
    assert (await b.check("ip:1"))[0] is True
    assert (await a.check("ip:1"))[0] is True
    assert (await b.check("ip:1"))[0] is False  # 4th hit across both instances
    # A different key is unaffected.
    assert (await a.check("ip:2"))[0] is True
    await client.aclose()


async def test_redis_separate_keys_independent():
    client = fakeredis.aioredis.FakeRedis()
    limiter = RedisSlidingWindowLimiter(client, times=1, window_seconds=60)
    assert (await limiter.check("a"))[0] is True
    assert (await limiter.check("a"))[0] is False
    assert (await limiter.check("b"))[0] is True
    await client.aclose()
