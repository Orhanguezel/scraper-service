from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from src.config import get_settings
from src.schemas.scrape import ScrapeRequest


@dataclass(frozen=True)
class FetchResult:
    response: Any
    html: str
    text: str
    final_url: str | None
    status_code: int | None


def _response_html(response: Any) -> str:
    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        return body.decode(getattr(response, "encoding", "utf-8") or "utf-8", errors="replace")
    if body:
        return str(body)
    return str(response.get()) if hasattr(response, "get") else ""


def _browser_kwargs(request: ScrapeRequest) -> dict[str, Any]:
    settings = get_settings()
    timeout_seconds = request.options.timeout or settings.default_timeout_seconds
    kwargs: dict[str, Any] = {
        "headless": request.options.headless,
        "network_idle": request.options.network_idle,
        "timeout": timeout_seconds * 1000,
        "block_ads": request.options.block_ads,
        "google_search": request.options.google_search,
    }
    if request.options.wait_for:
        kwargs["wait_selector"] = request.options.wait_for
    if request.options.user_agent:
        kwargs["useragent"] = request.options.user_agent
    return kwargs


def _fast_kwargs(request: ScrapeRequest) -> dict[str, Any]:
    settings = get_settings()
    headers = {}
    if request.options.user_agent:
        headers["User-Agent"] = request.options.user_agent
    return {
        "timeout": request.options.timeout or settings.default_timeout_seconds,
        "headers": headers,
    }


def _fetch_sync(request: ScrapeRequest) -> FetchResult:
    from scrapling.fetchers import DynamicFetcher, Fetcher, StealthyFetcher

    url = str(request.url)
    if request.mode == "fast":
        response = Fetcher.get(url, **_fast_kwargs(request))
    elif request.mode == "dynamic":
        response = DynamicFetcher.fetch(url, **_browser_kwargs(request))
    else:
        kwargs = _browser_kwargs(request)
        kwargs["solve_cloudflare"] = request.options.solve_cloudflare
        response = StealthyFetcher.fetch(url, **kwargs)

    html = _response_html(response)
    text = str(response.get_all_text(separator="\n", strip=True)) if hasattr(response, "get_all_text") else ""
    return FetchResult(
        response=response,
        html=html,
        text=text,
        final_url=getattr(response, "url", None),
        status_code=getattr(response, "status", None),
    )


async def fetch_page(request: ScrapeRequest) -> FetchResult:
    return await asyncio.to_thread(_fetch_sync, request)
