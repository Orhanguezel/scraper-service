from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import app
from src.lib.redis_client import get_redis, MemoryRedis


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEYS", "scraper-job-key")
    get_settings.cache_clear()
    redis = MemoryRedis()
    app.dependency_overrides[get_redis] = lambda: redis
    yield TestClient(app)
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_places_job_create_returns_202(monkeypatch, client):
    fake_pool = MagicMock()
    fake_pool.enqueue_job = AsyncMock()
    fake_pool.close = AsyncMock()

    async def fake_create_pool(_):
        return fake_pool

    monkeypatch.setattr("src.routes.jobs.create_pool", fake_create_pool)

    r = client.post(
        "/api/v1/jobs",
        headers={"Authorization": "Bearer scraper-job-key"},
        json={
            "type": "places-google-maps",
            "payload": {"query": "eczane", "total": 5, "language": "tr"},
            "callback_url": "https://example.com/hook",
            "callback_secret": "secret123456",
        },
    )
    assert r.status_code == 202
    assert fake_pool.enqueue_job.await_count == 1
    call = fake_pool.enqueue_job.await_args
    assert call.args[0] == "run_places_job"


def test_scrape_job_still_supported(monkeypatch, client):
    fake_pool = MagicMock()
    fake_pool.enqueue_job = AsyncMock()
    fake_pool.close = AsyncMock()

    async def fake_create_pool(_):
        return fake_pool

    monkeypatch.setattr("src.routes.jobs.create_pool", fake_create_pool)

    r = client.post(
        "/api/v1/jobs",
        headers={"Authorization": "Bearer scraper-job-key"},
        json={
            "type": "scrape",
            "payload": {"url": "https://example.com", "mode": "fast"},
        },
    )
    assert r.status_code == 202
    call = fake_pool.enqueue_job.await_args
    assert call.args[0] == "run_scrape_job"


def test_spider_job_returns_400(client):
    r = client.post(
        "/api/v1/jobs",
        headers={"Authorization": "Bearer scraper-job-key"},
        json={
            "type": "spider",
            "payload": {},
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "unsupported_job_type"
