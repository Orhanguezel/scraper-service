from datetime import datetime, timezone

from fastapi import HTTPException, status
from redis.asyncio import Redis


def _quota_day_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def enforce_daily_quota(redis: Redis, key_hash: str, namespace: str, limit: int) -> None:
    day = _quota_day_utc()
    redis_key = f"quota:{namespace}:{key_hash}:{day}"
    count = await redis.incr(redis_key)
    if count == 1:
        await redis.expire(redis_key, 90_000)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="daily_quota_exceeded",
        )
