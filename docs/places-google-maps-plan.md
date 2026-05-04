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
- [x] `tests/integration/test_places_route.py`, `test_places_job.py`
- [x] Mevcut pytest yesil
- [ ] Manuel smoke (Docker + gercek query, or. `eczane konya` total=5)
- [ ] Manuel CAPTCHA / hizli ardisik istek davranisi

### Faz 5 — Dokumantasyon & Yayin
- [x] `docs/api.md`, `docs/client-integration.md`, `docs/lead-competitor-architecture.md`, `README.md`
- [x] `pyproject.toml` / `src/main.py` 0.2.0, `CHANGELOG.md`

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
