# Client Integration

GeoSerra calls the service only when `SCRAPER_URL` and `SCRAPER_API_KEY` are configured. Otherwise it keeps using the legacy Python scripts.

## Sync

```ts
await fetch(`${process.env.SCRAPER_URL}/api/v1/scrape`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.SCRAPER_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    url,
    mode: 'stealthy',
    options: { solve_cloudflare: true, headless: true },
    return_html: true,
    return_text: true,
  }),
});
```

## Async

Use `/api/v1/jobs` for longer crawls and optionally provide `callback_url` plus `callback_secret`. The callback body is signed with `X-Scraper-Signature`.
