import anyio
from redis.asyncio import Redis


class DomainRateLimiter:
    def __init__(self, redis: Redis, interval_ms: int) -> None:
        self.redis = redis
        self.interval_ms = interval_ms

    async def acquire(self, hostname: str) -> None:
        key = f"discovery:domain:{hostname.casefold()}"
        while not await self.redis.set(key, "1", nx=True, px=self.interval_ms):
            remaining = await self.redis.pttl(key)
            await anyio.sleep(max(remaining, 25) / 1000)
