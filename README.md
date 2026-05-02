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
