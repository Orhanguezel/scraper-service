from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.lib.quota import enforce_daily_quota, _quota_day_utc


class FakeRedis:
    def __init__(self) -> None:
        self._ints: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._ints[key] = self._ints.get(key, 0) + 1
        return self._ints[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.expires[key] = seconds
        return True


@pytest.mark.asyncio
async def test_enforce_daily_quota_under_limit():
    redis = FakeRedis()
    await enforce_daily_quota(redis, "abc", "places", 200)
    await enforce_daily_quota(redis, "abc", "places", 200)
    assert redis._ints["quota:places:abc:" + _quota_day_utc()] == 2


@pytest.mark.asyncio
async def test_enforce_daily_quota_exceeds_raises():
    redis = FakeRedis()
    await enforce_daily_quota(redis, "abc", "places", 2)
    await enforce_daily_quota(redis, "abc", "places", 2)
    with pytest.raises(HTTPException) as exc:
        await enforce_daily_quota(redis, "abc", "places", 2)
    assert exc.value.status_code == 429
    assert exc.value.detail == "daily_quota_exceeded"


@pytest.mark.asyncio
async def test_enforce_daily_quota_new_day_resets_counter():
    redis = FakeRedis()
    day1 = "2026-01-01"
    day2 = "2026-01-02"

    with patch("src.lib.quota._quota_day_utc", return_value=day1):
        await enforce_daily_quota(redis, "abc", "places", 2)
        await enforce_daily_quota(redis, "abc", "places", 2)
        with pytest.raises(HTTPException):
            await enforce_daily_quota(redis, "abc", "places", 2)

    with patch("src.lib.quota._quota_day_utc", return_value=day2):
        await enforce_daily_quota(redis, "abc", "places", 2)
        assert redis._ints["quota:places:abc:2026-01-02"] == 1
