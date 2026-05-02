from fastapi import APIRouter, Depends, Request
from redis.asyncio import Redis

from src.auth import ApiPrincipal, require_api_key
from src.engine.service import perform_scrape
from src.lib.ratelimit import enforce_rate_limit
from src.lib.redis_client import get_redis
from src.schemas.scrape import ScrapeRequest, ScrapeResponse

router = APIRouter(prefix="/api/v1", tags=["scrape"])


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape(
    payload: ScrapeRequest,
    request: Request,
    principal: ApiPrincipal = Depends(require_api_key),
    redis: Redis = Depends(get_redis),
) -> ScrapeResponse:
    await enforce_rate_limit(redis, principal.key_hash)
    cache_bypass = request.headers.get("cache-control", "").lower() == "no-cache"
    return await perform_scrape(payload, redis, cache_bypass=cache_bypass)
