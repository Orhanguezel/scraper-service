import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.engine.places import google_maps as gm
from src.lib.redis_client import MemoryRedis
from src.schemas.places import GoogleMapsSearchRequest, GoogleMapsSearchResponse, Place


def _ok_response(query: str) -> GoogleMapsSearchResponse:
    return GoogleMapsSearchResponse(
        success=True,
        query=query,
        total_found=1,
        duration_ms=1,
        cache_hit=False,
        fetched_at=datetime.now(timezone.utc),
        places=[Place(name="X", place_url="https://www.google.com/maps/place/x/@1.0,2.0,15z")],
    )


@pytest.mark.asyncio
async def test_search_places_cache_hit_skips_uncached_and_quota(monkeypatch):
    redis = MemoryRedis()
    req = GoogleMapsSearchRequest(query="cached-q", total=1, language="tr")
    key = gm._cache_key(req)
    cached = _ok_response(req.query)
    await redis.set(key, json.dumps(cached.model_dump(mode="json")))

    uncached = AsyncMock()
    monkeypatch.setattr(gm, "_search_places_uncached", uncached)

    out = await gm.search_places(req, redis, key_hash="kh1")

    assert out.cache_hit is True
    uncached.assert_not_called()


@pytest.mark.asyncio
async def test_search_places_quota_on_miss_after_cache_exhausted(monkeypatch):
    redis = MemoryRedis()

    class S:
        places_daily_quota = 2
        places_proxy_url = ""

    monkeypatch.setattr(gm, "get_settings", lambda: S())

    async def fake_uncached(req, proxy_url=None):
        return _ok_response(req.query)

    uncached = AsyncMock(side_effect=fake_uncached)
    monkeypatch.setattr(gm, "_search_places_uncached", uncached)

    await gm.search_places(
        GoogleMapsSearchRequest(query="q1", total=1, language="tr"), redis, key_hash="u1"
    )
    await gm.search_places(
        GoogleMapsSearchRequest(query="q2", total=1, language="tr"), redis, key_hash="u1"
    )
    with pytest.raises(HTTPException) as exc:
        await gm.search_places(
            GoogleMapsSearchRequest(query="q3", total=1, language="tr"), redis, key_hash="u1"
        )
    assert exc.value.status_code == 429
    assert uncached.await_count == 2
