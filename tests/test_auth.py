import pytest
from fastapi import HTTPException

from src.auth import require_api_key
from src.config import get_settings


class FakeRedis:
    async def hgetall(self, key: str):
        return {}


@pytest.mark.asyncio
async def test_require_api_key_accepts_env_key(monkeypatch):
    monkeypatch.setenv("API_KEYS", "scraper-geoserra-test")
    get_settings.cache_clear()

    principal = await require_api_key("Bearer scraper-geoserra-test", get_settings(), FakeRedis())

    assert principal.project == "geoserra"


@pytest.mark.asyncio
async def test_require_api_key_rejects_missing_header(monkeypatch):
    monkeypatch.setenv("API_KEYS", "scraper-geoserra-test")
    get_settings.cache_clear()

    with pytest.raises(HTTPException) as exc:
        await require_api_key(None, get_settings(), FakeRedis())

    assert exc.value.status_code == 401
