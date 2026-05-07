from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl

ScrapeMode = Literal["fast", "stealthy", "dynamic"]
ScrapeProfile = Literal["geo-page", "geo-robots", "lead-page", "website-analysis", "directory-listing", "fair-exhibitor", "competitor-page"]
HttpMethod = Literal["GET", "POST"]


class ScrapeOptions(BaseModel):
    solve_cloudflare: bool = False
    wait_for: str | None = None
    headless: bool = True
    network_idle: bool = True
    timeout: int | None = Field(default=None, ge=1, le=120)
    user_agent: str | None = None
    block_ads: bool = True
    google_search: bool = False


class ScrapeRequest(BaseModel):
    url: HttpUrl
    mode: ScrapeMode = "fast"
    profile: ScrapeProfile | None = None
    selectors: dict[str, str] = Field(default_factory=dict)
    options: ScrapeOptions = Field(default_factory=ScrapeOptions)
    return_html: bool = False
    return_text: bool = False
    # POST destegi (sadece "fast" mode'da, curl-cffi impersonation ile).
    # form_data set edildiginde Content-Type: application/x-www-form-urlencoded gonderilir.
    method: HttpMethod = "GET"
    form_data: dict[str, str] | None = None
    json_body: dict[str, Any] | None = None
    extra_headers: dict[str, str] | None = None
    # Cookies forward + return (multi-step istekler icin: GET'le cookies'i al, POST'larda kullan).
    cookies: dict[str, str] | None = None
    return_cookies: bool = False


class ScrapeResponse(BaseModel):
    success: bool
    url: str
    profile: ScrapeProfile | None = None
    profile_version: str | None = None
    final_url: str | None
    status_code: int | None
    fetched_at: datetime
    cache_hit: bool
    duration_ms: int
    data: dict[str, Any] = Field(default_factory=dict)
    html: str | None = None
    text: str | None = None
    cookies: dict[str, str] | None = None
    error: str | None = None
