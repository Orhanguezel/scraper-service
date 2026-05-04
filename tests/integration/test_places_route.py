from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.lib.redis_client import MemoryRedis, get_redis
from src.main import app
from src.schemas.places import GoogleMapsSearchResponse, Place


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEYS", "scraper-test-key")
    get_settings.cache_clear()
    redis = MemoryRedis()
    app.dependency_overrides[get_redis] = lambda: redis
    yield TestClient(app)
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_places_route_requires_auth(client):
    r = client.post("/api/v1/places/google-maps", json={"query": "ab", "total": 3})
    assert r.status_code == 401


def test_places_route_total_over_10_returns_400(client):
    r = client.post(
        "/api/v1/places/google-maps",
        headers={"Authorization": "Bearer scraper-test-key"},
        json={"query": "kahve", "total": 15},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "total_exceeds_sync_limit_use_jobs_endpoint"


def test_places_route_success(monkeypatch, client):
    import src.routes.places as places_r

    async def fake_search(req, redis, *, cache_bypass=False, proxy_url=None, key_hash=""):
        return GoogleMapsSearchResponse(
            success=True,
            query=req.query,
            total_found=1,
            duration_ms=10,
            cache_hit=False,
            fetched_at=datetime.now(timezone.utc),
            places=[Place(name="X", place_url="https://www.google.com/maps/place/x/@1.0,2.0")],
        )

    monkeypatch.setattr(places_r, "search_places", fake_search)
    r = client.post(
        "/api/v1/places/google-maps",
        headers={"Authorization": "Bearer scraper-test-key"},
        json={"query": "kahve", "total": 5, "language": "tr"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["total_found"] == 1


def test_places_route_forwards_cache_bypass(monkeypatch, client):
    import src.routes.places as places_r

    seen: dict[str, bool] = {}

    async def fake_search(req, redis, *, cache_bypass=False, proxy_url=None, key_hash=""):
        seen["cache_bypass"] = cache_bypass
        return GoogleMapsSearchResponse(
            success=True,
            query=req.query,
            total_found=0,
            duration_ms=1,
            cache_hit=False,
            fetched_at=datetime.now(timezone.utc),
            places=[],
        )

    monkeypatch.setattr(places_r, "search_places", fake_search)
    client.post(
        "/api/v1/places/google-maps",
        headers={
            "Authorization": "Bearer scraper-test-key",
            "cache-control": "no-cache",
        },
        json={"query": "kahve", "total": 3},
    )
    assert seen.get("cache_bypass") is True
