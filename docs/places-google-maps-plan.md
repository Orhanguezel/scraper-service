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

> **Redis kota anahtari (uygulama):** `quota:places:{key_hash}:{YYYY-MM-DD}` — plandaki `places_quota:` yerine `quota:{namespace}:` kullanildi (`src/lib/quota.py`).

### 1.1 ToS Risk Azaltma
- [x] Plan onayi bolumu + README’de compliance / ToS / kamuya acik veri uyarisi.
- [x] Cevapta `place_url` alani (Maps URL) — kaynak izlenebilirligi (basarili kayitlarda doldurulur).
- [x] PII minimum: adres/telefon/web sitesi; kullanici yorumu metni toplu cekilmiyor.
- [x] Gunluk kota API anahtari basina (varsayilan 200, `PLACES_DAILY_QUOTA`).
- [x] `total` ust limiti **120** (`GoogleMapsSearchRequest`).

### 1.2 Bot Tespiti Karsi Onlemler (mevcut StealthyFetcher pattern'inden)
- [x] `playwright-stealth` + headless Chromium + argumanlar (`browser.py`).
- [x] UA havuzu (8) + rastgele viewport.
- [x] `Accept-Language` basligi `language` ile (`browser.py` `extra_http_headers`).
- [x] Dogrudan `/maps/search/...?hl=` URL ile gitme; detay sayfasina `goto(href)`.
- [x] Scroll arasi 800–1800 ms; detay oncesi 1200–2500 ms.
- [x] CAPTCHA: `recaptcha` iframe / form / “unusual traffic” / “i'm not a robot” metni; `error=captcha_detected`, **retry yok**.
- [x] Opsiyonel proxy: `PLACES_PROXY_URL` (bos = kapali).
- [ ] **Not:** Arq `max_jobs` simdilik **2** (scrape ile paylasimli); places icin **1** pilot sonrasi ayri karar.

### 1.3 Cache & Tekrar
- [x] Cache anahtari `places:gmaps:` + sha256(query,total,language,region); TTL **21600 s** (6 saat).
- [x] Cache hit `cache_hit=true`; kota sadece cache miss yolunda (`search_places`).

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
    test_places_engine.py      [YENI] URL/koordinat + HTML fixture parse
    test_quota.py              [YENI] gunluk kota
    test_browser.py            [YENI] UA/args sabitleri
  integration/
    test_places_route.py       [YENI] mock engine + auth + total limit
    test_places_job.py         [YENI] job enqueue + scrape regression
```

**Dokunulmayacak dosyalar (Places disi regression riski):**
- `src/routes/scrape.py`, `src/engine/service.py`, `src/engine/fetcher.py`, `src/engine/extractors.py`, `src/schemas/scrape.py`

**Places ile sinirli genisletme (planla uyumlu):**
- `src/main.py` (router include + versiyon)
- `src/routes/jobs.py` (job type branch + enqueue arg)
- `src/workers/tasks.py` (`WorkerSettings.functions`, `job_timeout`)
- `src/schemas/job.py` (`JobCreateRequest.type`, `payload` dict, `JobStatusResponse.result`)

---

## 3. Implementasyon Checklist

### Faz 0 — Hazirlik & Karar
- [x] Bu plani gozden gecir, GO/NO-GO ver. (**GO — 2026-05-04**)
- [x] Compliance bandi onayla (gunluk kota, total cap, headless-only).
- [x] Faz bolusumu: **1A → 1B → 1C → 2A → 2B → 3 → 4 → 5** ayri Composer oturumlari (PR birlestirme ayri karar).

### Faz 1 — Schema & Iskelet
- [x] `src/schemas/places.py` (PlacesOptions.timeout; headless istemci tarafindan verilemez — sunucu zorunlu headless)
- [x] `src/lib/quota.py` + `tests/unit/test_quota.py`
- [x] `src/engine/places/browser.py` (UA_POOL, launch 3-lu Playwright+Browser+Context, CAPTCHA, consent)
- [x] `src/engine/places/google_maps.py` (arama URL, scroll, listing href dedupe, detay `goto`, quota sadece cache miss, `places:gmaps:` cache)

### Faz 2 — API & Job
- [x] `src/routes/places.py` (sync total<=10, rate limit, cache-control; kota `search_places` icinde cache miss)
- [x] `src/workers/places_tasks.py` + `run_places_job` + `key_hash` enqueue
- [x] `src/workers/tasks.py` (`WorkerSettings.functions`, `job_timeout` 600)
- [x] `src/routes/jobs.py` + `src/schemas/job.py` (`places-google-maps`, payload dict)
- [x] `src/main.py` places router

### Faz 3 — Bagimliliklar & Build
- [x] `requirements.txt` (+ `setuptools<81` / `pkg_resources` — `playwright-stealth` uyumu)
- [x] `Dockerfile` chromium install
- [x] `docker-compose.yml` / `docker-compose.prod.yml` `shm_size: 1gb`
- [x] `.env.example` PLACES\_*

### Faz 4 — Test (otomatik)
- [x] `tests/unit/test_places_engine.py` + `tests/fixtures/maps_place_panel.html`
- [x] `tests/unit/test_search_places_cache_quota.py` (cache hit kota atlamasi; kota asimi)
- [x] `tests/integration/test_places_route.py`, `test_places_job.py`
- [x] Mevcut pytest yesil
- [ ] Manuel smoke (Docker + gercek query, or. `eczane konya` total=5)
- [ ] Manuel CAPTCHA / hizli ardisik istek davranisi

### Faz 5 — Dokumantasyon & Yayin
- [x] `docs/api.md`, `docs/client-integration.md`, `README.md` (lead mimari dokumanda Google Maps satiri istege bagli eklenebilir)
- [x] `pyproject.toml` / `src/main.py` 0.2.0, `CHANGELOG.md`

### Faz 6 — Deploy
- [ ] Local docker-compose ile end-to-end smoke (job + webhook).
- [ ] Staging/VPS'te `docker compose -f docker-compose.prod.yml build` (Chromium katmani ~500MB+).
- [x] Nginx: `nginx/scraper.conf` tum path’i `http://api:8200`’e proxy’ler — `/api/v1/places/*` icin ayri location gerekmez.
- [ ] PM2 / systemd worker restart (Arq `run_places_job` pickup).
- [ ] Pilot (GeoSerra / QuickEcommerce) ~1 hafta gozlem.

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

- [x] **Proxy:** `PLACES_PROXY_URL` env, varsayilan bos (kapali).
- [x] **Koordinat:** `place_url` icinden `@lat,lng` regex (`google_maps.py`).
- [x] **Kullanici yorumlari:** Cekilmiyor (PII riski) — karar: hayir.
- [x] **Email:** Faz disi (lead-monitor).
- [x] **Multi-region:** `region` -> `&gl=` (`_build_search_url`).
- [ ] **Worker queue / max_jobs:** Tek queue; `max_jobs=2` — pilot sonrasi 1 veya ayri queue degerlendirmesi.

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
