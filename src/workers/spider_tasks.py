import re
from typing import Any
from urllib.parse import urljoin, urlparse

from redis.asyncio import Redis
from scrapling.parser import Selector

from src.engine.service import perform_scrape
from src.schemas.job import JobStatus
from src.schemas.scrape import ScrapeRequest
from src.workers.shared import store_job, utc_now
from src.workers.webhook import post_callback


def _extract_internal_links(html: str, base_url: str, follow_patterns: list[str]) -> list[str]:
    sel = Selector(html, url=base_url)
    base_netloc = urlparse(base_url).netloc
    links: list[str] = []
    seen: set[str] = set()
    for a in sel.css("a[href]"):
        href = str(a.attrib.get("href", "")).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href).split("#")[0].split("?")[0]
        if not full.startswith(("http://", "https://")):
            continue
        if urlparse(full).netloc != base_netloc:
            continue
        if full in seen:
            continue
        if follow_patterns and not any(re.search(p, full, re.I) for p in follow_patterns):
            continue
        seen.add(full)
        links.append(full)
    return links


async def run_spider_job(
    ctx: dict[str, Any],
    job_id: str,
    payload: dict[str, Any],
    callback_url: str | None = None,
    callback_secret: str | None = None,
) -> dict[str, Any]:
    redis: Redis = ctx["redis"]
    await store_job(redis, job_id, status=JobStatus.running.value, updated_at=utc_now())

    start_url = str(payload.get("start_url", ""))
    max_pages = min(int(payload.get("max_pages", 20)), 50)
    profile = str(payload.get("profile", "lead-page"))
    follow_patterns: list[str] = payload.get("follow_patterns", [])

    results: list[dict[str, Any]] = []
    visited: set[str] = set()
    queue: list[str] = [start_url]

    try:
        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                request = ScrapeRequest.model_validate(
                    {"url": url, "profile": profile, "mode": "stealthy", "return_html": True, "return_text": True}
                )
                result = await perform_scrape(request, redis)
                results.append({"url": url, "data": result.data})

                if result.html and len(visited) < max_pages:
                    for link in _extract_internal_links(result.html, url, follow_patterns):
                        if link not in visited and link not in queue:
                            queue.append(link)
            except Exception as exc:
                results.append({"url": url, "data": None, "error": str(exc)})

        result_payload: dict[str, Any] = {
            "job_id": job_id,
            "status": JobStatus.done.value,
            "results": results,
            "pages_crawled": len(visited),
            "error": None,
        }
        await store_job(redis, job_id, status=JobStatus.done.value, result=result_payload, updated_at=utc_now())
        await post_callback(callback_url, callback_secret, result_payload)
        return result_payload
    except Exception as exc:
        error = str(exc)
        callback_payload: dict[str, Any] = {
            "job_id": job_id,
            "status": JobStatus.failed.value,
            "result": None,
            "error": error,
        }
        await store_job(redis, job_id, status=JobStatus.failed.value, error=error, updated_at=utc_now())
        await post_callback(callback_url, callback_secret, callback_payload)
        return callback_payload
