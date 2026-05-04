# Changelog

## 0.2.0 — 2026-05-04

### Changed

- Browser context sends `Accept-Language` from request `language`; CAPTCHA detection extended (unusual traffic / “not a robot” text).
- Unit tests for places cache hit (no uncached call) and daily quota on cache miss.

### Added

- Google Maps places search: `POST /api/v1/places/google-maps` (sync, `total` ≤ 10) and `POST /api/v1/jobs` with `type: "places-google-maps"` for larger batches (up to `total` 120 in payload).
- Playwright + `playwright-stealth` browser stack, six-hour Redis cache (`places:gmaps:*`), daily quota per API key (`quota:places:*`, `PLACES_DAILY_QUOTA`, default 200).
- Optional `PLACES_PROXY_URL` for Chromium launch proxy.
- Docker: Chromium install in image; `shm_size: 1gb` on API and worker services for browser stability.
