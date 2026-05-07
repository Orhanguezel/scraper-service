import json
from datetime import datetime, timezone
from uuid import uuid4

from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from src.auth import ApiPrincipal, require_api_key
from src.config import get_settings
from src.lib.ratelimit import enforce_rate_limit
from src.lib.redis_client import get_redis
from src.schemas.job import JobCreateRequest, JobCreateResponse, JobStatus, JobStatusResponse
from src.schemas.places import GoogleMapsSearchRequest
from src.schemas.scrape import ScrapeRequest
from src.workers.tasks import redis_settings_from_url

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


@router.post("/jobs", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    payload: JobCreateRequest,
    principal: ApiPrincipal = Depends(require_api_key),
    redis: Redis = Depends(get_redis),
) -> JobCreateResponse:
    await enforce_rate_limit(redis, principal.key_hash)

    if payload.type == "scrape":
        job_payload = ScrapeRequest.model_validate(payload.payload).model_dump(mode="json")
        function_name = "run_scrape_job"
    elif payload.type == "places-google-maps":
        job_payload = GoogleMapsSearchRequest.model_validate(payload.payload).model_dump(mode="json")
        function_name = "run_places_job"
    elif payload.type == "spider":
        job_payload = dict(payload.payload)
        function_name = "run_spider_job"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_job_type")

    job_id = uuid4().hex
    created_at = _now()
    await redis.hset(
        f"job:{job_id}",
        mapping={
            "job_id": job_id,
            "status": JobStatus.queued.value,
            "type": payload.type,
            "created_at": created_at,
            "updated_at": created_at,
            "project": principal.project,
        },
    )
    await redis.expire(f"job:{job_id}", 86_400)

    pool = await create_pool(redis_settings_from_url(get_settings().redis_url))
    try:
        cb = str(payload.callback_url) if payload.callback_url else None
        secret = payload.callback_secret
        if function_name == "run_places_job":
            await pool.enqueue_job(
                function_name,
                job_id,
                job_payload,
                cb,
                secret,
                principal.key_hash,
                _job_id=job_id,
            )
        else:
            await pool.enqueue_job(function_name, job_id, job_payload, cb, secret, _job_id=job_id)
    finally:
        await pool.close()

    return JobCreateResponse(job_id=job_id, status=JobStatus.queued, poll_url=f"/api/v1/jobs/{job_id}")


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: str,
    principal: ApiPrincipal = Depends(require_api_key),
    redis: Redis = Depends(get_redis),
) -> JobStatusResponse:
    await enforce_rate_limit(redis, principal.key_hash)
    raw = await redis.hgetall(f"job:{job_id}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")

    return JobStatusResponse(
        job_id=job_id,
        status=JobStatus(raw.get("status", JobStatus.failed.value)),
        type=raw.get("type", "scrape"),
        created_at=_loads(raw.get("created_at")),
        updated_at=_loads(raw.get("updated_at")),
        result=_loads(raw.get("result")),
        error=raw.get("error"),
    )
