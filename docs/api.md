# API

Bearer auth is required. API keys can be configured via `API_KEYS` or Redis records under `apikey:<sha256>`.

## POST /api/v1/scrape

### Selector Mode

```json
{
  "url": "https://example.com",
  "mode": "fast",
  "selectors": { "title": "title::text" },
  "return_html": false,
  "return_text": true
}
```

### GeoSerra `geo-page` Profile

When `profile` is set, `selectors` are ignored and `data` returns the frozen GeoSerra v1 page schema compatible with `fetch_page.py` scoring inputs.

```json
{
  "url": "https://example.com",
  "mode": "stealthy",
  "profile": "geo-page",
  "options": {
    "solve_cloudflare": true,
    "headless": true,
    "network_idle": true,
    "timeout": 90
  }
}
```

Response highlights:

```json
{
  "success": true,
  "profile": "geo-page",
  "profile_version": "v1",
  "data": {
    "title": "Example Domain",
    "description": "...",
    "h1_tags": [],
    "word_count": 120,
    "structured_data": [],
    "security_headers": {},
    "og_tags": {}
  }
}
```

### GeoSerra `geo-robots` Profile

```json
{
  "url": "https://example.com",
  "mode": "fast",
  "profile": "geo-robots"
}
```

Response highlights:

```json
{
  "success": true,
  "profile": "geo-robots",
  "profile_version": "v1",
  "data": {
    "url": "https://example.com/robots.txt",
    "exists": true,
    "ai_crawler_status": {
      "GPTBot": "ALLOWED"
    },
    "sitemaps": []
  }
}
```

## POST /api/v1/places/google-maps (sync)

Returns up to **10** places per request (`total` must be ≤ 10). Larger batches must use `POST /api/v1/jobs` with `type: "places-google-maps"`. Daily cap per API key: `PLACES_DAILY_QUOTA` (default 200). Send `Cache-Control: no-cache` to bypass the six-hour Redis cache for that query.

### Request

```json
{
  "query": "diş hekimi konya",
  "total": 5,
  "language": "tr",
  "region": "tr"
}
```

### Response

```json
{
  "success": true,
  "query": "diş hekimi konya",
  "total_found": 5,
  "duration_ms": 18450,
  "cache_hit": false,
  "fetched_at": "2026-05-04T10:12:00+00:00",
  "places": [
    {
      "name": "Örnek Klinik",
      "address": "Konya",
      "website": "https://example.com",
      "phone": "+90...",
      "reviews_count": 124,
      "reviews_average": 4.7,
      "place_type": "Diş kliniği",
      "opens_at": "08:00",
      "introduction": null,
      "place_url": "https://www.google.com/maps/place/...",
      "coordinates": { "lat": 37.87, "lng": 32.49 }
    }
  ],
  "error": null
}
```

## POST /api/v1/jobs

Queues a long-running job. Supported types: `scrape`, `places-google-maps`. `spider` returns `400 unsupported_job_type` until implemented.

```json
{
  "type": "scrape",
  "payload": {
    "url": "https://example.com",
    "mode": "stealthy",
    "return_text": true
  },
  "callback_url": "https://example.com/api/scraper/callback",
  "callback_secret": "change-me-long-secret"
}
```

### `places-google-maps` job

```json
{
  "type": "places-google-maps",
  "payload": {
    "query": "kuyumcu kayseri",
    "total": 50,
    "language": "tr",
    "region": "tr"
  },
  "callback_url": "https://example.com/api/scraper/callback",
  "callback_secret": "change-me-long-secret"
}
```

Poll `GET /api/v1/jobs/{job_id}` or consume the webhook callback (same `X-Scraper-Signature` scheme as scrape jobs).

## GET /api/v1/jobs/{job_id}

Returns `queued`, `running`, `done`, or `failed` with `result` or `error`.

Callbacks are signed with:

```text
X-Scraper-Signature: sha256=<hmac-sha256-body>
```
