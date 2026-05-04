# Places Provider — Projelerde Kullanim Rehberi

> **Servis URL'leri:**
> - Lokal: `http://localhost:8200`
> - Production: `https://scraper.guezelwebdesign.com`
>
> **Auth:** `Authorization: Bearer scraper-{project}-{secret}` formatinda API key.

> **Hizli smoke (repo):** `./scripts/places-smoke.sh` — varsayilan `http://127.0.0.1:8200`. Production: `SCRAPER_URL=https://scraper.guezelwebdesign.com SCRAPER_API_KEY='scraper-...' ./scripts/places-smoke.sh`

Bu rehber `scraper-service`'in `places/google-maps` endpoint'ini diger projelerden cagirmak icindir. Once kisa karar matrisi, sonra her stack icin kullanima hazir kod ornekleri.

---

## 1. Hangi Endpoint'i Ne Zaman?

| Senaryo | Endpoint | Neden |
|---------|----------|-------|
| Form submit, kullanici beklesin (1-10 sonuc) | `POST /api/v1/places/google-maps` | Sync, 15-30sn beklenir |
| Buyuk liste (10-120 sonuc), arka plan | `POST /api/v1/jobs` (`type=places-google-maps`) | Async + webhook, kullanici bekletmez |
| Cron / batch (gunluk lead toplama) | Job + webhook | Idempotent, tekrarlanabilir |
| Hizli demo / test | Sync, total=3 | Cache 6 saat, tekrar ucuz |

**Kural:** Sync endpoint **total>10 ile 400 doner**. Asma.

---

## 2. API Key Yonetimi

### 2.1 Yeni proje icin key olustur

```bash
# VPS'te scraper-service container'ina exec ol
ssh orhan@72.61.93.212
docker exec -it scraper-service python -c "
import secrets, hashlib
project = 'kamanilan'  # proje adi
secret = secrets.token_urlsafe(24)
key = f'scraper-{project}-{secret}'
print('API_KEY:', key)
print('SHA256:', hashlib.sha256(key.encode()).hexdigest())
"
```

Cikan `API_KEY` degerini iki yere koy:
1. **Scraper-service .env**: `API_KEYS=...,scraper-kamanilan-xxx` (virgulle ekle, mevcutleri silme)
2. **Tuketici proje .env**: `SCRAPER_API_KEY=scraper-kamanilan-xxx`

Container restart: `docker compose restart scraper-service worker`.

### 2.2 Per-project quota (opsiyonel, gelecek)

Su an global `PLACES_DAILY_QUOTA=200` tum projeler icin gecerli. Per-project quota gerekirse Redis'e:
```bash
redis-cli HSET apikey:<sha256> project kamanilan plan premium
# Plan kontrolu kodda implement edildiginde aktif olur (Faz 2 feature)
```

---

## 3. Compliance Checklist (Tuketici Proje)

Her tuketici projede su 4 madde dokumante olmali:

- [ ] Topladigim Google Maps verisi sadece kamuya acik isletme bilgisi (ad, adres, telefon, website, calisma saati, place type, rating).
- [ ] Veriyi musteriye gosterirken **`place_url` (Google Maps kaynak linki)** gosteriliyor — kullanici dogrulayabilir.
- [ ] Kullanici talep ederse veriyi siliyorum (KVKK/GDPR Right to Erasure).
- [ ] Toplama hizim mantikli (anlamsiz cron'lar yok). Cache 6 saat servis tarafinda zaten var.

---

## 4. Stack Bazli Ornekler

### 4.1 Next.js 16 (App Router, Server Action)

#### Sync — Form Submit
```ts
// app/actions/search-places.ts
'use server';

import { z } from 'zod';

const PlacesSchema = z.object({
  query: z.string().min(2).max(200),
  total: z.number().int().min(1).max(10),
  language: z.string().regex(/^[a-z]{2}$/).default('tr'),
});

export async function searchPlaces(input: z.infer<typeof PlacesSchema>) {
  const data = PlacesSchema.parse(input);
  const res = await fetch(`${process.env.SCRAPER_URL}/api/v1/places/google-maps`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.SCRAPER_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
    // Server timeout — sync endpoint 30sn'ye kadar surebilir
    signal: AbortSignal.timeout(45_000),
    cache: 'no-store',
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`scraper_error:${res.status}:${err.detail ?? 'unknown'}`);
  }

  return res.json() as Promise<{
    success: boolean;
    query: string;
    total_found: number;
    places: Array<{
      name: string;
      address: string | null;
      website: string | null;
      phone: string | null;
      reviews_count: number | null;
      reviews_average: number | null;
      place_type: string | null;
      opens_at: string | null;
      place_url: string | null;
      coordinates: { lat: number; lng: number } | null;
    }>;
    cache_hit: boolean;
    duration_ms: number;
    error: string | null;
  }>;
}
```

#### Async — Job + Webhook Callback

**Job baslat:**
```ts
// app/api/leads/scan/route.ts
import { NextResponse } from 'next/server';
import crypto from 'node:crypto';

export async function POST(req: Request) {
  const { query, total, projectId } = await req.json();

  const callbackSecret = crypto.randomBytes(24).toString('hex');
  // Bu secret'i DB'ye job_id ile birlikte sakla — webhook'ta dogrulama icin

  const res = await fetch(`${process.env.SCRAPER_URL}/api/v1/jobs`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.SCRAPER_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      type: 'places-google-maps',
      payload: { query, total, language: 'tr', region: 'tr' },
      callback_url: `${process.env.PUBLIC_URL}/api/leads/scan/callback`,
      callback_secret: callbackSecret,
    }),
  });

  const { job_id, status, poll_url } = await res.json();

  await db.insert(scanJobs).values({
    jobId: job_id,
    projectId,
    callbackSecret,
    status,
    query,
    createdAt: new Date(),
  });

  return NextResponse.json({ jobId: job_id, status });
}
```

**Callback handler (HMAC dogrulama):**
```ts
// app/api/leads/scan/callback/route.ts
import { NextResponse } from 'next/server';
import crypto from 'node:crypto';

export async function POST(req: Request) {
  const signature = req.headers.get('x-scraper-signature') ?? '';
  const body = await req.text(); // RAW body — JSON.parse ETME, hash kirilir

  const payload = JSON.parse(body);
  const job = await db.query.scanJobs.findFirst({ where: eq(scanJobs.jobId, payload.job_id) });
  if (!job) return NextResponse.json({ error: 'unknown_job' }, { status: 404 });

  const expected = 'sha256=' + crypto
    .createHmac('sha256', job.callbackSecret)
    .update(body)
    .digest('hex');

  if (!crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) {
    return NextResponse.json({ error: 'invalid_signature' }, { status: 401 });
  }

  if (payload.status === 'done') {
    await db.transaction(async (tx) => {
      for (const place of payload.result.places) {
        await tx.insert(leads).values({
          projectId: job.projectId,
          jobId: job.jobId,
          name: place.name,
          phone: place.phone,
          website: place.website,
          address: place.address,
          rating: place.reviews_average,
          reviewsCount: place.reviews_count,
          sourceUrl: place.place_url, // KVKK: kaynak link zorunlu
          lat: place.coordinates?.lat,
          lng: place.coordinates?.lng,
          rawJson: place,
          createdAt: new Date(),
        }).onConflictDoNothing(); // dedupe by sourceUrl unique index
      }
      await tx.update(scanJobs).set({ status: 'done', finishedAt: new Date() })
        .where(eq(scanJobs.jobId, job.jobId));
    });
  } else if (payload.status === 'failed') {
    await db.update(scanJobs).set({
      status: 'failed',
      error: payload.error,
      finishedAt: new Date(),
    }).where(eq(scanJobs.jobId, job.jobId));
  }

  return NextResponse.json({ ok: true });
}
```

**Polling fallback (callback ulasmazsa):**
```ts
// app/api/leads/scan/[jobId]/route.ts
export async function GET(req: Request, { params }: { params: { jobId: string } }) {
  const res = await fetch(`${process.env.SCRAPER_URL}/api/v1/jobs/${params.jobId}`, {
    headers: { Authorization: `Bearer ${process.env.SCRAPER_API_KEY}` },
  });
  return NextResponse.json(await res.json());
}
```

---

### 4.2 Fastify (TypeScript)

```ts
// src/services/scraper.service.ts
import { FastifyBaseLogger } from 'fastify';

export class ScraperService {
  constructor(
    private readonly baseUrl: string,
    private readonly apiKey: string,
    private readonly log: FastifyBaseLogger,
  ) {}

  async searchPlacesSync(query: string, total = 5) {
    if (total > 10) throw new Error('use_jobs_endpoint_for_total_gt_10');

    const res = await fetch(`${this.baseUrl}/api/v1/places/google-maps`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query, total, language: 'tr', region: 'tr' }),
      signal: AbortSignal.timeout(45_000),
    });

    if (!res.ok) {
      const err = await res.text();
      this.log.error({ status: res.status, err }, 'scraper_failed');
      throw new Error(`scraper_${res.status}`);
    }

    return res.json();
  }

  async startPlacesJob(opts: {
    query: string;
    total: number;
    callbackUrl: string;
    callbackSecret: string;
  }) {
    const res = await fetch(`${this.baseUrl}/api/v1/jobs`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        type: 'places-google-maps',
        payload: { query: opts.query, total: opts.total, language: 'tr' },
        callback_url: opts.callbackUrl,
        callback_secret: opts.callbackSecret,
      }),
    });
    return res.json();
  }
}

// plugins/scraper.plugin.ts
import fp from 'fastify-plugin';
import { ScraperService } from '../services/scraper.service';

declare module 'fastify' {
  interface FastifyInstance {
    scraper: ScraperService;
  }
}

export default fp(async (fastify) => {
  fastify.decorate('scraper', new ScraperService(
    process.env.SCRAPER_URL!,
    process.env.SCRAPER_API_KEY!,
    fastify.log,
  ));
});
```

**Webhook route (HMAC verify):**
```ts
// src/routes/scraper-callback.ts
import crypto from 'node:crypto';

export default async function (fastify: FastifyInstance) {
  fastify.post('/api/scraper/callback', {
    config: {
      // Raw body lazim, JSON parser bypass
      rawBody: true,
    },
  }, async (req, reply) => {
    const signature = req.headers['x-scraper-signature'] as string;
    const body = req.rawBody as string;
    const payload = JSON.parse(body);

    const job = await fastify.db.query.scanJobs.findFirst({
      where: (t, { eq }) => eq(t.jobId, payload.job_id),
    });
    if (!job) return reply.code(404).send({ error: 'unknown_job' });

    const expected = 'sha256=' + crypto
      .createHmac('sha256', job.callbackSecret)
      .update(body)
      .digest('hex');

    if (!crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) {
      return reply.code(401).send({ error: 'invalid_signature' });
    }

    // ... DB upsert (Next.js ornegine bak)
    return { ok: true };
  });
}
```

---

### 4.3 Laravel 12 (PHP)

```php
// app/Services/ScraperService.php
<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class ScraperService
{
    public function __construct(
        private readonly string $baseUrl,
        private readonly string $apiKey,
    ) {}

    public function searchPlacesSync(string $query, int $total = 5): array
    {
        if ($total > 10) {
            throw new \InvalidArgumentException('Use jobs endpoint for total > 10');
        }

        $response = Http::withToken($this->apiKey)
            ->timeout(45)
            ->post("{$this->baseUrl}/api/v1/places/google-maps", [
                'query' => $query,
                'total' => $total,
                'language' => 'tr',
                'region' => 'tr',
            ]);

        if ($response->failed()) {
            Log::error('scraper_places_failed', [
                'status' => $response->status(),
                'body' => $response->body(),
            ]);
            $response->throw();
        }

        return $response->json();
    }

    public function startPlacesJob(string $query, int $total, string $callbackUrl, string $callbackSecret): array
    {
        return Http::withToken($this->apiKey)
            ->post("{$this->baseUrl}/api/v1/jobs", [
                'type' => 'places-google-maps',
                'payload' => [
                    'query' => $query,
                    'total' => $total,
                    'language' => 'tr',
                ],
                'callback_url' => $callbackUrl,
                'callback_secret' => $callbackSecret,
            ])
            ->throw()
            ->json();
    }
}

// app/Providers/AppServiceProvider.php (boot)
$this->app->singleton(ScraperService::class, fn () => new ScraperService(
    config('services.scraper.url'),
    config('services.scraper.key'),
));

// config/services.php
'scraper' => [
    'url' => env('SCRAPER_URL'),
    'key' => env('SCRAPER_API_KEY'),
],
```

**Webhook controller:**
```php
// app/Http/Controllers/ScraperCallbackController.php
public function handle(Request $request)
{
    $body = $request->getContent(); // raw
    $signature = $request->header('X-Scraper-Signature', '');
    $payload = json_decode($body, true);

    $job = ScanJob::where('job_id', $payload['job_id'])->firstOrFail();

    $expected = 'sha256=' . hash_hmac('sha256', $body, $job->callback_secret);
    if (!hash_equals($expected, $signature)) {
        return response()->json(['error' => 'invalid_signature'], 401);
    }

    if ($payload['status'] === 'done') {
        DB::transaction(function () use ($payload, $job) {
            foreach ($payload['result']['places'] as $place) {
                Lead::updateOrCreate(
                    ['project_id' => $job->project_id, 'source_url' => $place['place_url']],
                    [
                        'name' => $place['name'],
                        'phone' => $place['phone'] ?? null,
                        'website' => $place['website'] ?? null,
                        'address' => $place['address'] ?? null,
                        'rating' => $place['reviews_average'] ?? null,
                        'reviews_count' => $place['reviews_count'] ?? null,
                        'lat' => $place['coordinates']['lat'] ?? null,
                        'lng' => $place['coordinates']['lng'] ?? null,
                        'raw_json' => $place,
                    ],
                );
            }
            $job->update(['status' => 'done', 'finished_at' => now()]);
        });
    }

    return response()->json(['ok' => true]);
}
```

---

### 4.4 Flutter (Dart)

Mobil app'ten direkt cagirma — **public anonim API key kullanma**. Backend'in proxy'lemeli (Fastify/Laravel route uzerinden). Eger zorunlu ise:

```dart
// lib/services/scraper_service.dart
import 'package:dio/dio.dart';

class ScraperService {
  final Dio _dio;

  ScraperService({required String baseUrl, required String apiKey})
    : _dio = Dio(BaseOptions(
        baseUrl: baseUrl,
        headers: {'Authorization': 'Bearer $apiKey'},
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 45),
      ));

  Future<List<Place>> searchPlaces(String query, {int total = 5}) async {
    if (total > 10) throw ArgumentError('Use jobs endpoint for total > 10');

    final res = await _dio.post('/api/v1/places/google-maps', data: {
      'query': query,
      'total': total,
      'language': 'tr',
      'region': 'tr',
    });

    return (res.data['places'] as List)
      .map((j) => Place.fromJson(j))
      .toList();
  }
}
```

**Tavsiye:** Mobile direkt cagri yerine `your-backend.com/api/places/search` proxy endpoint yaz. API key sunucuda kalsin.

---

## 5. Cron / Batch Job Pattern

### Gunluk lead taraması (Bun cron):

```ts
// scripts/daily-leads-cron.ts
import 'dotenv/config';

const QUERIES = [
  'eczane konya',
  'kuyumcu kayseri',
  'kafe ankara cankaya',
];

for (const query of QUERIES) {
  await fetch(`${process.env.SCRAPER_URL}/api/v1/jobs`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.SCRAPER_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      type: 'places-google-maps',
      payload: { query, total: 50, language: 'tr', region: 'tr' },
      callback_url: `${process.env.PUBLIC_URL}/api/leads/scan/callback`,
      callback_secret: process.env.SCRAPER_CALLBACK_SECRET,
    }),
  });
  // Yavas tut — Maps'i kazanmayalim
  await new Promise(r => setTimeout(r, 5000));
}
```

PM2 cron:
```bash
pm2 start scripts/daily-leads-cron.ts --cron "0 3 * * *" --no-autorestart --name leads-daily
```

---

## 6. Hata Yonetimi

| HTTP | detail | Anlami | Aksiyon |
|------|--------|--------|---------|
| 401 | `missing_bearer_token` / `invalid_api_key` | Auth | API key kontrol |
| 429 | `rate_limit_exceeded` | Dakikalik limit | Exponential backoff retry |
| 429 | `daily_quota_exceeded` | Gunluk kota | Retry **YAPMA**, ertesi gun bekle veya quota arttir |
| 400 | `total_exceeds_sync_limit_use_jobs_endpoint` | total>10 sync | Jobs endpoint'ine gec |
| 500 | server | Beklenmedik | Log + 1 kez retry |
| Job result `error="captcha_detected"` | CAPTCHA | Maps kustu | **Retry YOK**, frequency dusur, query degistir |

Recommended retry policy (Next.js ornek):
```ts
async function withRetry<T>(fn: () => Promise<T>, max = 2): Promise<T> {
  let lastErr: unknown;
  for (let i = 0; i < max; i++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      const msg = String(err);
      if (msg.includes('429') || msg.includes('captcha')) throw err; // retry yok
      await new Promise(r => setTimeout(r, 2000 * (i + 1)));
    }
  }
  throw lastErr;
}
```

---

## 7. Veri Modeli Onerisi (DB)

Tuketici projede asagidaki sema iyi calisir (Drizzle/Prisma uyumlu):

```sql
CREATE TABLE leads (
  id              BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  project_id      BIGINT UNSIGNED NOT NULL,
  source          VARCHAR(32) NOT NULL DEFAULT 'google_maps',
  source_url      VARCHAR(512) NOT NULL,           -- Google Maps place URL
  name            VARCHAR(255) NOT NULL,
  phone           VARCHAR(64),
  website         VARCHAR(512),
  address         TEXT,
  place_type      VARCHAR(128),
  opens_at        VARCHAR(64),
  rating          DECIMAL(2,1),
  reviews_count   INT UNSIGNED,
  lat             DECIMAL(10,7),
  lng             DECIMAL(10,7),
  raw_json        JSON,
  query           VARCHAR(255),                     -- hangi aramayla geldi
  scan_job_id     VARCHAR(64),
  first_seen_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uniq_project_source (project_id, source_url),
  INDEX idx_project_query (project_id, query),
  INDEX idx_phone (phone),
  INDEX idx_geo (lat, lng)
);

CREATE TABLE scan_jobs (
  job_id           VARCHAR(64) PRIMARY KEY,
  project_id       BIGINT UNSIGNED NOT NULL,
  query            VARCHAR(255) NOT NULL,
  total_requested  INT UNSIGNED NOT NULL,
  total_found      INT UNSIGNED,
  status           ENUM('queued','running','done','failed') NOT NULL,
  error            TEXT,
  callback_secret  VARCHAR(64) NOT NULL,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at      TIMESTAMP NULL
);
```

`UNIQUE (project_id, source_url)` ile **dedupe otomatik** — `ON DUPLICATE KEY UPDATE` ile `last_seen_at` ve `raw_json` guncellenir.

---

## 8. Monitoring

VPS'te kontrol:
```bash
# Quota kullanimi (bugune ait)
docker exec scraper-redis redis-cli KEYS "quota:places:*:$(date -u +%Y-%m-%d)"
docker exec scraper-redis redis-cli MGET $(docker exec scraper-redis redis-cli KEYS "quota:places:*:$(date -u +%Y-%m-%d)")

# Aktif job sayisi
docker exec scraper-redis redis-cli ZCARD arq:queue

# Son 10 job durumu (project bazli)
docker exec scraper-redis redis-cli KEYS "job:*" | head -10
```

Application log:
```bash
docker logs -f scraper-service --tail 100 | grep -i 'places\|captcha\|quota'
docker logs -f scraper-worker --tail 100
```

---

## 9. Sik Sorulan Sorular

**S: Cache 6 saat — fiyat degisimi kaciririm mi?**
C: Ayni `query+total+language+region` kombinasyonu icin. Farkli query veya `Cache-Control: no-cache` header'i ile bypass mumkun.

**S: total=120'den fazla istesem?**
C: Maps zaten ~120 sonra gostermeyi keser. Farkli query'lere bol (mahalle bazli, kategori bazli).

**S: Kullanici yorumlari da gerek.**
C: Plan disi (PII riski + 10x scraping suresi). Lead-monitor servisi ayri bir feature'da degerlendirilir.

**S: Backend'siz mobile'den cagirayim mi?**
C: API key bundle'dan sizar. Backend proxy yaz.

**S: Birden fazla kullanici ayni anda istek atarsa?**
C: Worker `max_jobs=1` (places concurrency 1). Kuyrukta beklerler. Sync endpoint tek tek calisir.

**S: Test ortami?**
C: `SCRAPER_URL=http://localhost:8200` + lokal docker compose. API key `.env`'de `API_KEYS=scraper-test-localdev` set et, ayni key'i tuketici .env'ine yaz.
