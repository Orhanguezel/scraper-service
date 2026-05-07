from typing import Any
from arq.connections import RedisSettings
from redis.asyncio import Redis

from src.config import get_settings
from src.engine.service import perform_scrape
from src.schemas.job import JobStatus
from src.schemas.scrape import ScrapeRequest
from src.workers.places_tasks import run_places_job
from src.workers.shared import store_job, utc_now
from src.workers.spider_tasks import run_spider_job
from src.workers.webhook import post_callback

# Public aliases kept for any callers that import these from tasks.py
_store_job = store_job


async def run_scrape_job(
    ctx: dict[str, Any],
    job_id: str,
    payload: dict[str, Any],
    callback_url: str | None = None,
    callback_secret: str | None = None,
) -> dict[str, Any]:
    redis: Redis = ctx["redis"]
    await store_job(redis, job_id, status=JobStatus.running.value, updated_at=utc_now())

    try:
        request = ScrapeRequest.model_validate(payload)
        result = await perform_scrape(request, redis)
        result_payload = result.model_dump(mode="json")
        await store_job(redis, job_id, status=JobStatus.done.value, result=result_payload, updated_at=utc_now())
        callback_payload = {"job_id": job_id, "status": JobStatus.done.value, "result": result_payload, "error": None}
        await post_callback(callback_url, callback_secret, callback_payload)
        return callback_payload
    except Exception as exc:
        error = str(exc)
        await store_job(redis, job_id, status=JobStatus.failed.value, error=error, updated_at=utc_now())
        callback_payload = {"job_id": job_id, "status": JobStatus.failed.value, "result": None, "error": error}
        await post_callback(callback_url, callback_secret, callback_payload)
        return callback_payload


def redis_settings_from_url(url: str) -> RedisSettings:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "redis",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").lstrip("/") or "0"),
        password=parsed.password,
    )


class WorkerSettings:
    functions = [run_scrape_job, run_places_job, run_spider_job]
    redis_settings = redis_settings_from_url(get_settings().redis_url)
    max_jobs = 2
    job_timeout = 600
