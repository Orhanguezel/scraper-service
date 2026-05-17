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
    cookies: dict[str, str] | None = None


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
    headers: dict[str, str] = {}
    if request.options.user_agent:
        headers["User-Agent"] = request.options.user_agent
    if request.extra_headers:
        headers.update(request.extra_headers)
    kwargs: dict[str, Any] = {
        "timeout": request.options.timeout or settings.default_timeout_seconds,
        "headers": headers,
    }
    if request.cookies:
        kwargs["cookies"] = request.cookies
    return kwargs


def _extract_cookies(response: Any) -> dict[str, Any] | None:
    """Scrapling response'tan cookies dict cikar. Yoksa None doner.

    curl-cffi response objesinde `cookies` (Cookies veya RequestsCookieJar) varsa onu donerir;
    Playwright response'larinda bu alan olmayabilir, simdilik None.
    """
    raw = getattr(response, "cookies", None)
    if raw is None:
        return None
    try:
        if hasattr(raw, "items"):
            return {str(k): str(v) for k, v in raw.items()}
        if hasattr(raw, "get_dict"):
            return {str(k): str(v) for k, v in raw.get_dict().items()}
        return {str(c.name): str(c.value) for c in raw}
    except Exception:
        return None


def _fetch_sync(request: ScrapeRequest) -> FetchResult:
    from scrapling.fetchers import DynamicFetcher, Fetcher, StealthyFetcher

    url = str(request.url)
    if request.mode == "fast":
        kwargs = _fast_kwargs(request)
        if request.method == "POST":
            if request.json_body is not None:
                kwargs["json"] = request.json_body
            elif request.form_data is not None:
                kwargs["data"] = request.form_data
            response = Fetcher.post(url, **kwargs)
        else:
            response = Fetcher.get(url, **kwargs)
    elif request.mode == "dynamic":
        # Browser-based POST henuz desteklenmiyor; method GET varsayilir.
        response = DynamicFetcher.fetch(url, **_browser_kwargs(request))
    else:
        kwargs = _browser_kwargs(request)
        kwargs["solve_cloudflare"] = request.options.solve_cloudflare
        # Browser-based POST henuz desteklenmiyor; method GET varsayilir.
        response = StealthyFetcher.fetch(url, **kwargs)

    html = _response_html(response)
    text = str(response.get_all_text(separator="\n", strip=True)) if hasattr(response, "get_all_text") else ""
    cookies = _extract_cookies(response) if request.return_cookies else None
    return FetchResult(
        response=response,
        html=html,
        text=text,
        final_url=getattr(response, "url", None),
        status_code=getattr(response, "status", None),
        cookies=cookies,
    )


async def fetch_page(request: ScrapeRequest) -> FetchResult:
    # "fast" mode is a plain HTTP client (no browser); only the browser-backed
    # Scrapling modes need to honour the global concurrency cap.
    if request.mode == "fast":
        return await asyncio.to_thread(_fetch_sync, request)

    from src.engine.places.browser import browser_semaphore

    async with browser_semaphore():
        return await asyncio.to_thread(_fetch_sync, request)
