from __future__ import annotations

import random
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright_stealth import stealth_async

UA_POOL: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

VIEWPORTS: list[tuple[int, int]] = [
    (1366, 768),
    (1536, 864),
    (1920, 1080),
    (1440, 900),
]

CHROMIUM_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-features=IsolateOrigins,site-per-process",
]


def _timezone_for_language(language: str) -> str:
    if language == "tr":
        return "Europe/Istanbul"
    return "UTC"


async def apply_stealth_to_page(page: Page) -> None:
    await stealth_async(page)


async def launch_stealth_context(
    language: str,
    proxy_url: str | None = None,
) -> tuple[Playwright, Browser, BrowserContext]:
    ua = random.choice(UA_POOL)
    viewport = random.choice(VIEWPORTS)
    pw = await async_playwright().start()
    launch_kwargs: dict[str, Any] = {"headless": True, "args": CHROMIUM_ARGS}
    if proxy_url:
        launch_kwargs["proxy"] = {"server": proxy_url}
    browser = await pw.chromium.launch(**launch_kwargs)
    locale = f"{language}-{language.upper()}"
    context = await browser.new_context(
        user_agent=ua,
        viewport={"width": viewport[0], "height": viewport[1]},
        locale=locale,
        timezone_id=_timezone_for_language(language),
    )
    return pw, browser, context


async def detect_captcha(page: Page) -> bool:
    for sel in ('iframe[src*="recaptcha"]', "div#captcha-form"):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible(timeout=1_000):
                return True
        except Exception:
            continue
    try:
        body = (await page.content()).lower()
        if "unusual traffic from your computer network" in body:
            return True
    except Exception:
        pass
    return False


async def dismiss_consent(page: Page) -> None:
    consent_selectors = (
        'button[aria-label*="Reddet"]',
        'button[aria-label*="Reject"]',
        'button:has-text("Tümünü reddet")',
        'button:has-text("Reject all")',
    )
    for sel in consent_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click(timeout=2_000)
                return
        except Exception:
            continue
