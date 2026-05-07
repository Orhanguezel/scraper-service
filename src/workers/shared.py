import json
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def store_job(redis: Redis, job_id: str, **fields: Any) -> None:
    serialised = {
        key: json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
        for key, value in fields.items()
        if value is not None
    }
    if serialised:
        await redis.hset(f"job:{job_id}", mapping=serialised)
        await redis.expire(f"job:{job_id}", 86_400)
