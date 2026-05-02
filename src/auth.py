import hashlib
from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis

from src.config import Settings, get_settings
from src.lib.redis_client import get_redis


@dataclass(frozen=True)
class ApiPrincipal:
    key_hash: str
    project: str
    plan: str = "default"


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _project_from_key(api_key: str) -> str:
    parts = api_key.split("-")
    if len(parts) >= 3 and parts[0] == "scraper":
        return parts[1]
    return "unknown"


async def require_api_key(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> ApiPrincipal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_bearer_token")

    api_key = authorization.split(" ", 1)[1].strip()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="empty_bearer_token")

    key_hash = _hash_key(api_key)
    redis_record = await redis.hgetall(f"apikey:{key_hash}")
    if redis_record:
        project = redis_record.get("project", _project_from_key(api_key))
        plan = redis_record.get("plan", "default")
        return ApiPrincipal(key_hash=key_hash, project=project, plan=plan)

    if api_key in settings.api_key_set:
        return ApiPrincipal(key_hash=key_hash, project=_project_from_key(api_key))

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_api_key")
