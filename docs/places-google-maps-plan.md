# Google Maps Places Provider — Implementasyon Plani

## Plan onayi (GO / NO-GO)

| Alan | Karar |
|------|--------|
| Durum | **GO** — implementasyona baslanabilir |
| Tarih | 2026-05-04 |
| Compliance bandi | Onayli: gunluk kota (varsayilan 200), sync `total` ust limiti 10, async/job ust limiti 120, headless-only, CAPTCHA’da retry yok |
| Faz stratejisi | Plan dosyasindaki **Faz 1A → 1B → 1C → 2A → 2B → 3 → 4 → 5** sirasi; her faz ayri Cursor Composer oturumu |
| Bilinen eksik | `../Google-Maps-Scrapper/main.py` bu workspace’te yok; Faz 1C oncesi XPath kaynagi saglanmali veya eski `main.py` icerigi plana/fixture’a alinmali |

Faz 0 checklist bu onayla kapatildi: plan gozden gecirildi, compliance bandi ve faz bolusumu netlesti.

---

> Amac: scraper-service icine Google Maps isletme arama (places search) yetenegi eklemek.
> Sart 1: Mevcut `scrape` / `jobs` akisini bozma.
> Sart 2: Bot tespiti / yasal risk minimumda. Sadece kamuya acik veri.
> Pattern: Mevcut `ScrapeRequest -> perform_scrape -> Arq job -> webhook` zincirinin **paraleli**.

---

## 0. Mimari Karar Ozeti

- Yeni bir **resource**: `places` (URL bazli `scrape` ile karistirma).
- Yeni profile mantigi degil, **ayri schema + ayri engine module + ayri route**.
- Sync HTTP destekli ama varsayilan **job-based** (search 30-90sn surer; HTTP timeout'a takilma).
- Browser stack'i: `playwright.async_api` (Scrapling fetcher'lari URL fetch icin tasarlanmis; Maps'in scroll+click+SPA davranisi `page_action` ile zorlanir, dogal degil).
- Scrapling **kalir**, sadece `places` tarafinda kullanilmaz. Mevcut `geo-page`, `geo-robots`, klasik scrape akislari aynen calisir.
- Anti-bot stratejisi mevcut `StealthyFetcher` mantigini taklit eder: stealth plugin + user-agent rotasyonu + rastgele bekleme + headless + cookies persistence.
- Compliance: `places` namespace'i icin ayri kota, sadece kamuya acik isletme verisi, kullanim notu README'de.

---

## 1. Yasal & Anti-bot Stratejisi (Karar Onceligi)

### 1.1 ToS Risk Azaltma
- [ ] `docs/places-google-maps-plan.md` (bu dosya) icine "compliance" bolumu eklendi.
- [ ] Public README'ye **"Bu provider sadece kamuya acik isletme verisi icindir; Google Maps ToS'unu sen okumalisin"** uyarisi eklenecek.
- [ ] Sonuclarda `source_url` (Google Maps place URL) zorunlu — veri kaynagi izlenebilir kalsin.
- [ ] PII alanlari minimum: telefon/website/adres OK; ozel inceleme/kullanici yorumu cekme YOK.
- [ ] Per-API-key gunluk kota (Redis sayac): `places_quota:{key_hash}:{YYYY-MM-DD}`. Default 200 sorgu/gun.
- [ ] Kullanici `--total` ust limiti **120** (DOM'dan tasidiginda Maps zaten kesiyor; 200+ talep abuse sinyali).

### 1.2 Bot Tespiti Karsi Onlemler (mevcut StealthyFetcher pattern'inden)
- [ ] `playwright-stealth` paketi (`tf-playwright-stealth` veya `playwright-stealth` aktif fork) — Scrapling'in StealthyFetcher'i da bunu kullaniyor.
- [ ] Headless **true** ama Chromium argumanlariyla:
  - `--disable-blink-features=AutomationControlled`
  - `--no-sandbox`
  - `--disable-dev-shm-usage`
  - viewport 1366x768 / 1920x1080 random
- [ ] User-Agent havuzu (5-10 modern Chrome UA), her job baslarken random sec.
- [ ] `Accept-Language` header request'in `language` parametresine gore (`tr-TR,tr;q=0.9` veya `en-US,en;q=0.9`).
- [ ] Maps'a dogrudan **arama URL'si** ile git: `https://www.google.com/maps/search/<encoded query>?hl=<lang>` — searchbox'a tiklamak yerine. Daha az event, daha az risk.
- [ ] Scroll loop: her scroll arasinda `random.uniform(800, 1800)` ms bekle.
- [ ] Place click arasinda `random.uniform(1200, 2500)` ms bekle.
- [ ] CAPTCHA tespiti: `text=robot` / `iframe[src*="recaptcha"]` selector — varsa job'i `failed` + `error="captcha_detected"` ile bitir, retry **YAPMA** (cezayi buyutur).
- [ ] (Opsiyonel — Faz 2) `PROXY_URL` env: residential/rotating proxy support. Default yok.
- [ ] Concurrency: `max_jobs` default `1` bu provider icin. Arq tarafinda `places_jobs_max=1` ayri queue dusunulebilir (Faz 2). Faz 1: shared queue ama places job'lar icinde browser launch lock.

### 1.3 Cache & Tekrar
- [ ] Cache key: `places:gmaps:sha256(query|total|language|region)`, TTL **6 saat** (default 24h yerine kisa — fiyat/saat degisir).
- [ ] Cache hit cevabi `cache_hit=true` ile doner; quota dusurulmez.

---

## 2. Klasor / Dosya Plani (Mevcut Yapiya Eklenecek)

```
src/
  schemas/
    places.py                  [YENI] GoogleMapsSearchRequest, Place, GoogleMapsSearchResponse
  engine/
    places/
      __init__.py              [YENI]
      google_maps.py           [YENI] async search + extract
      browser.py               [YENI] stealth playwright launcher (UA rotation, args)
  routes/
    places.py                  [YENI] POST /api/v1/places/google-maps (sync, kucuk total)
  workers/
    places_tasks.py            [YENI] run_places_job (Arq function)
  lib/
    quota.py                   [YENI] daily quota helper (places namespace)
docs/
  places-google-maps-plan.md   [BU DOSYA]
tests/
  unit/
    test_places_extract.py     [YENI] HTML fixture'tan parse testi
  integration/
    test_places_route.py       [YENI] mock'lu route testi
```

**Dokunulmayacak dosyalar (regression riski):**
- `src/main.py` (sadece router include eklenecek)
- `src/routes/scrape.py`, `src/routes/jobs.py`
- `src/engine/service.py`, `src/engine/fetcher.py`, `src/engine/extractors.py`
- `src/schemas/scrape.py`, `src/schemas/job.py`
- `src/workers/tasks.py` (ayri dosyaya yazacagiz, WorkerSettings.functions listesine ekleme)

---

## 3. Implementasyon Checklist

### Faz 0 — Hazirlik & Karar
- [x] Bu plani gozden gecir, GO/NO-GO ver. (**GO — 2026-05-04**)
- [x] Compliance bandi onayla (gunluk kota, total cap, headless-only).
- [x] Faz bolusumu: **1A → 1B → 1C → 2A → 2B → 3 → 4 → 5** ayri Composer oturumlari (PR birlestirme ayri karar).

### Faz 1 — Schema & Iskelet
- [ ] `src/schemas/places.py`:
  - [ ] `GoogleMapsSearchRequest` (query, total<=120, language, region, options)
  - [ ] `Place` (name, address, website, phone, reviews_count, reviews_average, place_type, opens_at, introduction, place_url, coordinates)
  - [ ] `GoogleMapsSearchResponse` (success, query, total_found, places, duration_ms, fetched_at, cache_hit, error)
  - [ ] `PlacesOptions` (timeout, language, headless=True forced, user_agent override yok — guvenlik)
- [ ] `src/lib/quota.py`:
  - [ ] `enforce_daily_quota(redis, key_hash, namespace, limit)` fonksiyonu
  - [ ] Rate-limit yaninda cagrilacak (mevcut `ratelimit.py`'a dokunma)
- [ ] `src/engine/places/browser.py`:
  - [ ] `UA_POOL` listesi
  - [ ] `async launch_stealth_context(language)` — playwright async, stealth args, random UA, viewport
  - [ ] CAPTCHA detect helper
- [ ] `src/engine/places/google_maps.py`:
  - [ ] `async search_places(req) -> GoogleMapsSearchResponse`
  - [ ] Search URL pattern (`/maps/search/...?hl=`), arama girisi yok
  - [ ] Scroll-until-enough loop (random sleep)
  - [ ] Listing toplama, deduplicate by place URL
  - [ ] Her listing icin click + extract (mevcut XPath'ler `main.py`'den + place_url + lat/lng URL'den parse)
  - [ ] CAPTCHA / consent dialog handling (`text=Reddet` / `Reject all` gibi)
  - [ ] Cache wrap (`places:gmaps:` prefix)

### Faz 2 — API & Job
- [ ] `src/routes/places.py`:
  - [ ] `POST /api/v1/places/google-maps` (sync, **total<=10 zorunlu**, daha buyukse 400 + "use job endpoint")
  - [ ] `require_api_key` + `enforce_rate_limit` + `enforce_daily_quota("places", 200)`
  - [ ] `cache-control: no-cache` header destegi (mevcut scrape gibi)
- [ ] `src/workers/places_tasks.py`:
  - [ ] `async run_places_job(ctx, job_id, payload, callback_url, callback_secret)`
  - [ ] Status update + webhook callback (mevcut `tasks.py` patternini birebir taklit et, kod kopyala — abstract'e gerek yok)
- [ ] `src/workers/tasks.py` icindeki `WorkerSettings.functions` listesine `run_places_job` import + ekle (TEK satirlik degisiklik, regression riski dusuk).
- [ ] `src/routes/jobs.py` icindeki `JobCreateRequest.type` literal'ina `"places-google-maps"` ekle:
  - [ ] `payload` validasyonu type'a gore branch
  - [ ] `pool.enqueue_job("run_places_job", ...)` cagrisi
  - [ ] Mevcut `"scrape"` davranisi **AYNEN** kalmali — switch/case ile ayir, `if/elif` yapısı kur.
- [ ] `src/main.py`'a `places_router` include et.

### Faz 3 — Bagimliliklar & Build
- [ ] `requirements.txt`:
  - [ ] `playwright>=1.44.0,<2.0.0`
  - [ ] `playwright-stealth>=1.0.6` (veya `tf-playwright-stealth`)
- [ ] `Dockerfile`:
  - [ ] `RUN python -m playwright install chromium --with-deps` (base image'da varsa skip — kontrol)
  - [ ] Ekstra Chromium dependency'lerini kontrol (`libnss3`, `libxkbcommon0` vb. base'de olmali ama dogrula)
- [ ] `docker-compose.yml` ve `docker-compose.prod.yml`:
  - [ ] Worker service'in `shm_size: 1gb` ayarla (Chromium icin sart, yoksa crash).
  - [ ] `PLACES_DAILY_QUOTA` env eklenebilir (default 200).
- [ ] `.env.example`'a:
  - [ ] `PLACES_DAILY_QUOTA=200`
  - [ ] `PLACES_PROXY_URL=` (bos default, dokumantasyonu var)

### Faz 4 — Test
- [ ] `tests/unit/test_places_extract.py`:
  - [ ] Sabit HTML fixture (Maps detay paneli kopyasi) ile `extract_place_from_dom` parse testi
  - [ ] Eksik alan toleransi (yorum yok, telefon yok vb.)
- [ ] `tests/integration/test_places_route.py`:
  - [ ] Engine'i mock'la, route 202/200 + auth + quota davranisi
  - [ ] Cache hit testi
  - [ ] Quota asimi -> 429 testi
- [ ] Mevcut `pytest`'in kirilmadigini dogrula (`bun run` analogu yok, dogrudan `pytest` veya `uv run pytest`).
- [ ] Manuel smoke: tek query (`"eczane konya"`, total=5) job ile cek, cevabi gor.
- [ ] Manuel CAPTCHA testi: bilerek hizli ardisik 5 job at, `captcha_detected` error donmesini ve retry yapmamasini dogrula.

### Faz 5 — Dokumantasyon & Yayin
- [ ] `docs/api.md`'ye `/api/v1/places/google-maps` endpoint'i + ornek payload + response.
- [ ] `docs/client-integration.md`'ye TypeScript ornegi (job create + poll).
- [ ] `docs/lead-competitor-architecture.md`'da "source_type=google-maps" provider olarak referans ver.
- [ ] `README.md`'ye 1 paragraf compliance uyarisi.
- [ ] Versiyon bump: `pyproject.toml` 0.1.0 -> 0.2.0.
- [ ] CHANGELOG (yoksa olustur).

### Faz 6 — Deploy
- [ ] Local docker-compose ile end-to-end smoke (job + webhook).
- [ ] Staging/VPS'te `docker compose -f docker-compose.prod.yml build scraper-service` (Chromium katmani buyur, ~500MB+ — boyut kabul edilebilir mi karar).
- [ ] Nginx tarafinda yeni endpoint icin ozel ayar gerekmez (zaten `/api/v1/*` proxy'lenmis olmali — dogrula).
- [ ] PM2 / systemd worker restart (mevcut Arq worker yeni function'i pickup etsin).
- [ ] Pilot proje (GeoSerra veya QuickEcommerce) ile 1 hafta test, hata oranini gozle.

---

## 4. API Sozlesmesi (Taslak)

### Sync (kucuk total)
```http
POST /api/v1/places/google-maps
Authorization: Bearer scraper-geoserra-xxx
Content-Type: application/json

{
  "query": "diş hekimi konya",
  "total": 5,
  "language": "tr",
  "region": "tr"
}
```

### Async (varsayilan)
```http
POST /api/v1/jobs
{
  "type": "places-google-maps",
  "payload": {
    "query": "kuyumcu kayseri",
    "total": 50,
    "language": "tr"
  },
  "callback_url": "https://geoserra.com/api/scraper/callback",
  "callback_secret": "min8char_secret"
}
```

### Response (sync veya job result)
```json
{
  "success": true,
  "query": "diş hekimi konya",
  "total_found": 5,
  "duration_ms": 18450,
  "cache_hit": false,
  "fetched_at": "2026-05-04T10:12:00Z",
  "places": [
    {
      "name": "...",
      "address": "...",
      "website": "https://...",
      "phone": "+90...",
      "reviews_count": 124,
      "reviews_average": 4.7,
      "place_type": "Diş kliniği",
      "opens_at": "08:00",
      "introduction": "...",
      "place_url": "https://www.google.com/maps/place/...",
      "coordinates": { "lat": 37.87, "lng": 32.49 }
    }
  ],
  "error": null
}
```

---

## 5. Risk Defteri

| Risk | Olasilik | Etki | Azaltim |
|------|----------|------|---------|
| Maps DOM degisimi (XPath bozulur) | Yuksek | Orta | XPath'ler tek dosyada (`engine/places/google_maps.py`); fixture testi kirilirsa hizli yakalanir. |
| CAPTCHA ile karsilasma | Orta | Yuksek | Stealth + UA rotasyon + kota + retry yok. Proxy faz 2. |
| Google IP banlama | Dusuk-Orta | Yuksek | Quota + concurrency=1 + random sleep. Pilot'ta gozle. |
| Chromium image boyutu | Yuksek | Dusuk | Tek base image (zaten Scrapling'de var olabilir). Dogrula. |
| ToS sikayeti | Dusuk | Yuksek | Sadece public business data, kullanim notu, source_url tracking, kullanici sozlesmesi. |
| Mevcut scrape akisina regresyon | Dusuk | Yuksek | Ayri dosyalar, sadece 3 dosyada eklenti (`main.py`, `routes/jobs.py`, `workers/tasks.py`). PR'da diff kucuk tut. |

---

## 6. Bilinmeyenler / Karar Bekleyenler

- [ ] **Proxy stratejisi**: Faz 1'de hic mi yok, yoksa env destegi ekleyip kullanmayalim mi? (Oneri: env destegi ekle, default kapali.)
- [ ] **Coordinates parse**: `place_url`'den `@lat,lng,zoom` regex ile cikarilabilir, ek istek yok. (Oneri: faz 1'e dahil.)
- [ ] **Kullanici yorumlari**: Cekmiyoruz (PII riski). Karar: hayir.
- [ ] **Email cikarma (place website'inden)**: Faz disi. Lead-monitor servisinin isi.
- [ ] **Multi-region**: `region` query param simdilik `&gl=tr` shape'inde URL'ye bind. Test edilecek.
- [ ] **Worker queue ayrimi**: Tek queue mi, places ayri queue mu? Faz 1: tek queue, `max_jobs=1` global.

---

## 7. Calisma Bolusumu (Orkestrasyon)

| Asama | Sorumlu Arac |
|-------|--------------|
| Plan & sema tasarimi | **Claude Code** (bitti — bu dosya) |
| Schema + engine + route + worker kodu | **Codex** |
| Docker / Playwright kurulum dogrulama | **Codex + DevOps agent** |
| Browser davranis dogrulama (gercek arama) | **Antigravity** |
| Lint / autocomplete cila | **Copilot** |

Codex bu plani okuyup `Faz 1` -> `Faz 6` sirayla implement edecek. Her faz sonunda Claude Code review eder.
