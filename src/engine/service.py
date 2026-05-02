import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from redis.asyncio import Redis

from src.engine.extractors import extract_basic_page_data, extract_geo_page, extract_geo_robots
from src.engine.fetcher import fetch_page
from src.engine.selectors import extract_selectors
from src.lib.cache import build_cache_key, get_cached, set_cached
from src.schemas.scrape import ScrapeRequest, ScrapeResponse


def _robots_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


async def perform_scrape(
    payload: ScrapeRequest,
    redis: Redis,
    *,
    cache_bypass: bool = False,
) -> ScrapeResponse:
    cache_key = build_cache_key(payload)

    if not cache_bypass:
        cached = await get_cached(redis, cache_key)
        if cached:
            cached["cache_hit"] = True
            if not payload.return_html:
                cached["html"] = None
            if not payload.return_text:
                cached["text"] = None
            return ScrapeResponse.model_validate(cached)

    started = time.perf_counter()
    fetch_payload = payload
    if payload.profile == "geo-robots":
        fetch_payload = ScrapeRequest.model_validate(
            {
                **payload.model_dump(mode="json"),
                "url": _robots_url(str(payload.url)),
                "mode": "fast",
                "profile": payload.profile,
            }
        )

    fetched = await fetch_page(fetch_payload)

    if payload.profile == "geo-page":
        data = extract_geo_page(fetched.html, str(payload.url), fetched.response)
    elif payload.profile == "geo-robots":
        data = extract_geo_robots(fetched.text or fetched.html, str(fetch_payload.url), fetched.status_code)
    else:
        data = extract_basic_page_data(fetched.response)
        data.update(extract_selectors(fetched.response, payload.selectors))

    duration_ms = int((time.perf_counter() - started) * 1000)

    response = ScrapeResponse(
        success=True,
        url=str(payload.url),
        profile=payload.profile,
        profile_version="v1" if payload.profile else None,
        final_url=fetched.final_url,
        status_code=fetched.status_code,
        fetched_at=datetime.now(timezone.utc),
        cache_hit=False,
        duration_ms=duration_ms,
        data=data,
        html=fetched.html if payload.return_html else None,
        text=fetched.text if payload.return_text else None,
    )
    await set_cached(redis, cache_key, response.model_dump(mode="json"))
    return response
