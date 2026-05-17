from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, Playwright
from redis.asyncio import Redis

from src.config import get_settings
from src.engine.places.browser import (
    apply_stealth_to_page,
    browser_semaphore,
    close_stealth_context,
    detect_captcha,
    dismiss_consent,
    launch_stealth_context,
)
from src.lib.quota import enforce_daily_quota
from src.schemas.places import (
    Coordinates,
    GoogleMapsSearchRequest,
    GoogleMapsSearchResponse,
    Place,
)

logger = logging.getLogger(__name__)

CACHE_PREFIX = "places:gmaps:"
CACHE_TTL_SECONDS = 21_600
FEED_SELECTOR = 'div[role="feed"]'
LISTING_SELECTOR = 'a[href*="/maps/place/"]'
PLACE_NAME_SELECTOR = "h1.DUwDvf"


def _build_search_url(query: str, language: str, region: str | None) -> str:
    encoded = quote_plus(query)
    url = f"https://www.google.com/maps/search/{encoded}?hl={language}"
    if region:
        url += f"&gl={region}"
    return url


def _parse_coordinates(place_url: str | None) -> Coordinates | None:
    if not place_url:
        return None
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", place_url)
    if not m:
        return None
    return Coordinates(lat=float(m.group(1)), lng=float(m.group(2)))


def _parse_reviews_from_text(text: str) -> tuple[int | None, float | None]:
    m = re.search(r"\((\d+)\s*yorum\)", text, re.IGNORECASE)
    count = int(m.group(1)) if m else None
    rating_m = re.search(r"(\d+[.,]\d+)", text)
    avg: float | None = None
    if rating_m:
        avg = float(rating_m.group(1).replace(",", "."))
    return count, avg


def parse_place_from_panel_html(html: str) -> Place | None:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("h1.DUwDvf")
    if not h1:
        return None
    name = h1.get_text(strip=True)
    if not name:
        return None

    address = None
    addr_btn = soup.select_one('button[data-item-id="address"]')
    if addr_btn:
        span = addr_btn.select_one(".Io6YTe")
        address = (span or addr_btn).get_text(strip=True) or None

    website = None
    auth = soup.select_one('a[data-item-id="authority"]')
    if auth and auth.get("href"):
        website = str(auth["href"])

    phone = None
    tel = soup.select_one('a[href^="tel:"]')
    if tel:
        phone = tel.get_text(strip=True) or str(tel.get("href", "")).removeprefix("tel:")

    reviews_count: int | None = None
    reviews_average: float | None = None
    reviews_block = soup.select_one(".mgr77e")
    if reviews_block:
        chunk = reviews_block.get_text(" ", strip=True)
        sibling = reviews_block.find_next("span", class_=re.compile("fontBodySmall"))
        if sibling:
            chunk += " " + sibling.get_text(" ", strip=True)
        reviews_count, reviews_average = _parse_reviews_from_text(chunk)

    place_type = None
    type_btn = soup.select_one("button.DkEaL")
    if type_btn:
        place_type = type_btn.get_text(strip=True) or None

    opens_at = None
    hours_div = soup.select_one("div.t6gpPc.fontBodySmall")
    if hours_div:
        opens_at = hours_div.get_text(strip=True) or None

    introduction = None
    intro = soup.select_one("div.PYvSYb")
    if intro:
        introduction = intro.get_text(strip=True) or None

    return Place(
        name=name,
        address=address,
        website=website,
        phone=phone,
        place_type=place_type,
        opens_at=opens_at,
        introduction=introduction,
        reviews_count=reviews_count,
        reviews_average=reviews_average,
        place_url=None,
        coordinates=None,
    )


def _cache_key(req: GoogleMapsSearchRequest) -> str:
    payload = {
        "query": req.query,
        "total": req.total,
        "language": req.language,
        "region": req.region,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"{CACHE_PREFIX}{digest}"


def _place_href_to_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return urljoin("https://www.google.com", href)


async def _scroll_until_enough(page: Page, target: int, scroll_panel_selector: str) -> int:
    panel = page.locator(scroll_panel_selector).first
    await panel.wait_for(state="visible", timeout=15_000)
    last = 0
    for _ in range(30):
        links = await page.locator(LISTING_SELECTOR).count()
        if links >= target:
            return links
        if links == last and last > 0:
            break
        last = links
        await panel.evaluate("el => el.scrollBy(0, 900)")
        await page.wait_for_timeout(random.randint(800, 1800))
    return await page.locator(LISTING_SELECTOR).count()


async def _extract_place(page: Page) -> Place | None:
    html = await page.content()
    place = parse_place_from_panel_html(html)
    if not place:
        return None
    place_url = page.url
    coords = _parse_coordinates(place_url)
    return place.model_copy(update={"place_url": place_url, "coordinates": coords})


async def _search_places_uncached(
    req: GoogleMapsSearchRequest,
    proxy_url: str | None,
) -> GoogleMapsSearchResponse:
    t0 = time.perf_counter()
    fetched_at = datetime.now(timezone.utc)
    places: list[Place] = []
    timeout_ms = req.options.timeout * 1000
    async with browser_semaphore():
        pw: Playwright | None = None
        browser: Browser | None = None
        context: BrowserContext | None = None
        page: Page | None = None
        try:
            pw, browser, context = await launch_stealth_context(req.language, proxy_url)
            page = await context.new_page()
            await apply_stealth_to_page(page)
            await page.goto(
                _build_search_url(req.query, req.language, req.region),
                timeout=timeout_ms,
                wait_until="domcontentloaded",
            )
            await dismiss_consent(page)
            if await detect_captcha(page):
                return GoogleMapsSearchResponse(
                    success=False,
                    query=req.query,
                    total_found=0,
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    cache_hit=False,
                    fetched_at=fetched_at,
                    places=[],
                    error="captcha_detected",
                )
            await page.wait_for_selector(LISTING_SELECTOR, timeout=15_000)
            await _scroll_until_enough(page, req.total, FEED_SELECTOR)
            loc = page.locator(LISTING_SELECTOR)
            count = await loc.count()
            seen_hrefs: set[str] = set()
            hrefs: list[str] = []
            for i in range(count):
                href = await loc.nth(i).get_attribute("href")
                if not href or href in seen_hrefs:
                    continue
                seen_hrefs.add(href)
                hrefs.append(href)
                if len(hrefs) >= req.total:
                    break

            for href in hrefs:
                try:
                    await page.goto(_place_href_to_url(href), timeout=timeout_ms, wait_until="domcontentloaded")
                    await dismiss_consent(page)
                    await page.wait_for_selector(PLACE_NAME_SELECTOR, timeout=10_000)
                    await page.wait_for_timeout(random.randint(1200, 2500))
                    place = await _extract_place(page)
                    if place and place.name:
                        places.append(place)
                except Exception as exc:
                    logger.warning("places listing extract skipped: %s", exc)
                    continue

            duration_ms = int((time.perf_counter() - t0) * 1000)
            return GoogleMapsSearchResponse(
                success=True,
                query=req.query,
                total_found=len(places),
                duration_ms=duration_ms,
                cache_hit=False,
                fetched_at=fetched_at,
                places=places,
                error=None,
            )
        except Exception as exc:
            logger.exception("places search failed")
            return GoogleMapsSearchResponse(
                success=False,
                query=req.query,
                total_found=len(places),
                duration_ms=int((time.perf_counter() - t0) * 1000),
                cache_hit=False,
                fetched_at=fetched_at,
                places=places,
                error=str(exc),
            )
        finally:
            await close_stealth_context(pw, browser, context, page)


async def search_places(
    req: GoogleMapsSearchRequest,
    redis: Redis,
    *,
    cache_bypass: bool = False,
    proxy_url: str | None = None,
    key_hash: str,
) -> GoogleMapsSearchResponse:
    t0 = time.perf_counter()
    cache_key = _cache_key(req)
    if not cache_bypass:
        raw = await redis.get(cache_key)
        if raw:
            parsed = GoogleMapsSearchResponse.model_validate(json.loads(raw))
            return parsed.model_copy(
                update={
                    "cache_hit": True,
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                }
            )

    settings = get_settings()
    await enforce_daily_quota(redis, key_hash, "places", settings.places_daily_quota)

    result = await _search_places_uncached(req, proxy_url)
    if result.success:
        await redis.set(
            cache_key,
            json.dumps(result.model_dump(mode="json")),
            ex=CACHE_TTL_SECONDS,
        )
    return result
