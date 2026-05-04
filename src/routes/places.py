from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis

from src.auth import ApiPrincipal, require_api_key
from src.config import get_settings
from src.engine.places.google_maps import search_places
from src.lib.ratelimit import enforce_rate_limit
from src.lib.redis_client import get_redis
from src.schemas.places import GoogleMapsSearchRequest, GoogleMapsSearchResponse

router = APIRouter(prefix="/api/v1", tags=["places"])


@router.post("/places/google-maps", response_model=GoogleMapsSearchResponse)
async def google_maps_search(
    payload: GoogleMapsSearchRequest,
    request: Request,
    principal: ApiPrincipal = Depends(require_api_key),
    redis: Redis = Depends(get_redis),
) -> GoogleMapsSearchResponse:
    await enforce_rate_limit(redis, principal.key_hash)

    if payload.total > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="total_exceeds_sync_limit_use_jobs_endpoint",
        )

    cache_bypass = request.headers.get("cache-control", "").lower() == "no-cache"
    settings = get_settings()
    proxy = settings.places_proxy_url.strip() or None

    return await search_places(
        payload,
        redis,
        cache_bypass=cache_bypass,
        proxy_url=proxy,
        key_hash=principal.key_hash,
    )
