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

## Places (Google Maps)

### Sync (≤ 10 results)

```ts
const res = await fetch(`${process.env.SCRAPER_URL}/api/v1/places/google-maps`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.SCRAPER_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    query: 'kahveci konya',
    total: 5,
    language: 'tr',
    region: 'tr',
  }),
});
const data = await res.json();
```

### Async job

```ts
const job = await fetch(`${process.env.SCRAPER_URL}/api/v1/jobs`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.SCRAPER_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    type: 'places-google-maps',
    payload: { query: 'kuyumcu kayseri', total: 50, language: 'tr' },
    callback_url: `${process.env.PUBLIC_URL}/api/scraper/callback`,
    callback_secret: process.env.SCRAPER_CALLBACK_SECRET,
  }),
});
const { job_id, poll_url } = await job.json();
```

Poll `GET ${SCRAPER_URL}${poll_url}` until `status` is `done` or `failed`. The `result` object matches the sync places response shape.

### Callback verification

Same as scrape jobs: read raw body bytes, compute `sha256=HMAC_SHA256(secret, body)`, compare to `X-Scraper-Signature`. See `docs/places-usage-guide.md` for field notes and quotas.
