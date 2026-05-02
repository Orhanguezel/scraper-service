# GeoSerra Profiles

The GeoSerra integration uses profile-based extraction instead of raw HTML parsing.

## `geo-page`

- Fetches with the requested Scrapling mode, usually `stealthy`.
- Returns `data` in the same v1 shape expected by GeoSerra's former `fetch_page.py` scoring path.
- `profile_version` is fixed as `v1` so downstream scoring can reject future breaking changes deliberately.

Critical fields for comparison:

```text
is_https, title, description, h1_tags, word_count, structured_data,
has_hreflang, lang_attribute, og_tags, security_headers
```

## `geo-robots`

- Fetches `<origin>/robots.txt` with fast mode.
- Returns `ai_crawler_status` for GPTBot, ClaudeBot, PerplexityBot, Google-Extended, and other AI crawlers used by GeoSerra reports.

## Local Smoke

```bash
curl -X POST http://127.0.0.1:8200/api/v1/scrape \
  -H 'Authorization: Bearer scraper-geoserra-change-me' \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","mode":"fast","profile":"geo-page"}'
```
