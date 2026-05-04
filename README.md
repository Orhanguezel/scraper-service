# Scraper Service

Central FastAPI wrapper around Scrapling for portfolio projects.

## Local Dev

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn src.main:app --reload --host 0.0.0.0 --port 8200
```

## Docker

```bash
docker compose up --build
curl http://127.0.0.1:8200/health
```

## Example

```bash
curl -X POST http://127.0.0.1:8200/api/v1/scrape \
  -H 'Authorization: Bearer scraper-geoserra-change-me' \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","mode":"fast","return_html":true,"return_text":true}'
```

## Async Jobs

```bash
curl -X POST http://127.0.0.1:8200/api/v1/jobs \
  -H 'Authorization: Bearer scraper-geoserra-change-me' \
  -H 'Content-Type: application/json' \
  -d '{"type":"scrape","payload":{"url":"https://example.com","mode":"fast","return_text":true}}'
```

## Places provider (Google Maps)

`POST /api/v1/places/google-maps` extracts publicly visible business listings from Google Maps using a headless browser. **This provider is only for publicly visible business data; you must read and comply with Google Maps Terms of Service yourself.** Use it only for data you are entitled to collect. Each place in the response should include a `place_url` (Maps URL) so the source stays traceable. If Google shows a CAPTCHA, the request fails with `captcha_detected` and is not retried automatically. For more than ten results per call, use `POST /api/v1/jobs` with `type: "places-google-maps"` (see `docs/places-usage-guide.md`).

## Product Direction

Lead generation and competitor monitoring documents:

- [Product note](docs/lead-competitor-product.md)
- [MVP scope](docs/lead-competitor-mvp.md)
- [Technical architecture](docs/lead-competitor-architecture.md)
- [Roadmap](docs/lead-competitor-roadmap.md)
