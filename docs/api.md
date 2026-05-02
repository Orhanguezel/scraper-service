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

## POST /api/v1/jobs

Queues a long-running scrape. `spider` is reserved for the next milestone; F2 supports `scrape` jobs.

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

## GET /api/v1/jobs/{job_id}

Returns `queued`, `running`, `done`, or `failed` with `result` or `error`.

Callbacks are signed with:

```text
X-Scraper-Signature: sha256=<hmac-sha256-body>
```
