from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from src.lib.redis_client import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(redis: Redis = Depends(get_redis)) -> dict[str, str]:
    redis_status = "ok"
    try:
        await redis.ping()
    except Exception:
        redis_status = "unavailable"
    return {"status": "ok", "redis": redis_status, "browsers": "configured"}
