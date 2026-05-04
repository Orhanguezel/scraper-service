import json
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from src.config import get_settings
from src.engine.places.google_maps import search_places
from src.schemas.job import JobStatus
from src.schemas.places import GoogleMapsSearchRequest
from src.workers.webhook import post_callback


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _store_job(redis: Redis, job_id: str, **fields: Any) -> None:
    serialised = {
        key: json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
        for key, value in fields.items()
        if value is not None
    }
    if serialised:
        await redis.hset(f"job:{job_id}", mapping=serialised)
        await redis.expire(f"job:{job_id}", 86_400)


async def run_places_job(
    ctx: dict[str, Any],
    job_id: str,
    payload: dict[str, Any],
    callback_url: str | None = None,
    callback_secret: str | None = None,
    key_hash: str | None = None,
) -> dict[str, Any]:
    redis: Redis = ctx["redis"]
    await _store_job(redis, job_id, status=JobStatus.running.value, updated_at=utc_now())
    kh = key_hash or "unknown"

    try:
        request = GoogleMapsSearchRequest.model_validate(payload)
        settings = get_settings()
        proxy = settings.places_proxy_url.strip() or None
        result = await search_places(request, redis, proxy_url=proxy, key_hash=kh)
        result_payload = result.model_dump(mode="json")
        status = JobStatus.done.value if result.success else JobStatus.failed.value
        err = result.error if not result.success else None
        await _store_job(
            redis,
            job_id,
            status=status,
            result=result_payload,
            updated_at=utc_now(),
            error=err,
        )
        callback_payload = {
            "job_id": job_id,
            "status": status,
            "result": result_payload,
            "error": err,
        }
        await post_callback(callback_url, callback_secret, callback_payload)
        return callback_payload
    except Exception as exc:
        error = str(exc)
        await _store_job(redis, job_id, status=JobStatus.failed.value, error=error, updated_at=utc_now())
        callback_payload = {"job_id": job_id, "status": JobStatus.failed.value, "result": None, "error": error}
        await post_callback(callback_url, callback_secret, callback_payload)
        return callback_payload
