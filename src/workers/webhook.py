import hashlib
import hmac
import json
from typing import Any
import httpx


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def post_callback(
    callback_url: str | None,
    callback_secret: str | None,
    payload: dict[str, Any],
) -> None:
    if not callback_url:
        return

    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if callback_secret:
        headers["X-Scraper-Signature"] = sign_payload(callback_secret, body)

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(callback_url, content=body, headers=headers)
        response.raise_for_status()
