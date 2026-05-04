# Cursor Implementasyon Talimati — Google Maps Places Provider

> **Hedef agent**: Cursor Composer / Cursor Agent.
> **Mimari karar dosyasi**: `docs/places-google-maps-plan.md` (zorunlu okuma).
> **Yaklasim**: Plan dosyasini Cursor'a context olarak ver, asagidaki promptlari sirayla calistir. Her faz sonunda elle test/review.

---

## 0. Cursor'a Baslamadan Once

### 0.1 Cursor Settings (proje koku)
`.cursorrules` veya `.cursor/rules/scraper-places.mdc` dosyasini olustur:

```markdown
---
description: Google Maps places provider implementasyonu
globs: src/engine/places/**, src/schemas/places.py, src/routes/places.py, src/workers/places_tasks.py
alwaysApply: false
---

Bu projede asagidakiler ZORUNLUDUR:

1. **Mevcut akisi bozma**: src/routes/scrape.py, src/engine/service.py, src/engine/fetcher.py, src/engine/extractors.py, src/schemas/scrape.py dosyalarina dokunma. Sadece su dosyalara TEK satirlik ek yapilabilir:
   - src/main.py (router include)
   - src/routes/jobs.py (type literal + branch)
   - src/workers/tasks.py (WorkerSettings.functions listesi)

2. **Stack**: Python 3.11+, FastAPI, Pydantic v2, Redis async, Arq, playwright.async_api, playwright-stealth.

3. **Patterns**:
   - Mevcut auth (`require_api_key`) ve rate-limit (`enforce_rate_limit`) AYNEN kullan.
   - Mevcut webhook patternini (`post_callback`, `X-Scraper-Signature`) AYNEN kullan.
   - Cache ve quota Redis uzerinden, key prefix `places:gmaps:` ve `places_quota:`.

4. **Anti-bot kurallari**:
   - headless=True ZORUNLU, kullanici override edemez.
   - retry YOK; CAPTCHA yakalanirsa job direkt failed.
   - random sleep: scroll arasi 800-1800ms, click arasi 1200-2500ms.
   - total parametresi max 120.

5. **Test yazmadan PR yok**: Her yeni dosya icin pytest case'i.

6. **Kod stili**: type hints zorunlu, async/await tutarli, magic number yok (config'e cek).

7. **Yorum yazma**: Sadece WHY yaz, WHAT zaten kod. Comment'in eksik kalmasi yorum yazmaktan iyidir.
```

### 0.2 Plan Dosyasini Pin'le
Cursor chat'te `@docs/places-google-maps-plan.md` ile dosyayi context'e ekle. Her faz prompt'unda referans olsun.

### 0.3 Branch
```bash
git checkout -b feat/places-google-maps
```

---

## 1. Faz Faz Cursor Promptlari

Her prompt'u Cursor Composer'da AYRI bir oturum olarak calistir. Ayni oturumda zincirleme prompt YAPMA — context kirlenir, plan disina cikar. Her faz sonu: `git diff` review, lokal test, commit.

---

### Faz 1A — Schema & Quota Helper

**Cursor Prompt:**

````
@docs/places-google-maps-plan.md @src/schemas/scrape.py @src/lib/ratelimit.py @src/auth.py

Plan dosyasinin "Faz 1 — Schema & Iskelet" bolumunu uygula. Su dosyalari OLUSTUR:

1. src/schemas/places.py
   - PlacesOptions: timeout (int, default 60, le=180), proxy_url (str | None, default None — sadece env'den okunur, request'ten degil)
   - GoogleMapsSearchRequest:
     - query: str (min_length=2, max_length=200)
     - total: int (default 20, ge=1, le=120)
     - language: str (default "tr", regex=r"^[a-z]{2}$")
     - region: str | None (default None, regex=r"^[a-z]{2}$")
     - options: PlacesOptions (default factory)
   - Coordinates: lat: float, lng: float
   - Place: name (str), address, website, phone, place_type, opens_at, introduction (hepsi str | None)
     - reviews_count: int | None, reviews_average: float | None
     - place_url: str | None
     - coordinates: Coordinates | None
   - GoogleMapsSearchResponse:
     - success: bool
     - query: str
     - total_found: int
     - duration_ms: int
     - cache_hit: bool
     - fetched_at: datetime
     - places: list[Place]
     - error: str | None = None

2. src/lib/quota.py
   - async enforce_daily_quota(redis: Redis, key_hash: str, namespace: str, limit: int) -> None
   - Redis key: f"quota:{namespace}:{key_hash}:{YYYY-MM-DD UTC}"
   - INCR + EXPIRE 90000s (~25h, gun donumu garantisi)
   - Limit asilirsa HTTPException 429 detail="daily_quota_exceeded"
   - Mevcut ratelimit.py patternini birebir taklit et.

3. tests/unit/test_quota.py
   - Limit altinda gecer
   - Limit ustunde 429
   - Yeni gun (mock time) yeni sayac

KISITLAR:
- src/schemas/scrape.py'a ASLA dokunma.
- src/lib/ratelimit.py'a ASLA dokunma.
- pydantic v2 sentaksi (Field, model_config).
````

**Review:**
- `git diff` — sadece 3 yeni dosya gorulmeli
- `pytest tests/unit/test_quota.py -v`
- Commit: `feat(places): add schema and daily quota helper`

---

### Faz 1B — Browser Launcher

**Cursor Prompt:**

````
@docs/places-google-maps-plan.md @src/engine/fetcher.py

Plan dosyasinin "1.2 Bot Tespiti Karsi Onlemler" bolumunu uygula.

Olustur: src/engine/places/__init__.py (bos) ve src/engine/places/browser.py

src/engine/places/browser.py icerigi:

1. UA_POOL constant: 8 adet modern Chrome user-agent (Mac/Windows/Linux karisik, surum 120-130 araligi). Hardcode liste, magic yok.

2. VIEWPORTS constant: [(1366, 768), (1536, 864), (1920, 1080), (1440, 900)]

3. CHROMIUM_ARGS constant: aksi yazilmadikca asagidakiler:
   --disable-blink-features=AutomationControlled
   --no-sandbox
   --disable-dev-shm-usage
   --disable-gpu
   --disable-features=IsolateOrigins,site-per-process

4. async launch_stealth_context(language: str, proxy_url: str | None = None) -> tuple[Browser, BrowserContext]
   - playwright.async_api uzerinden chromium launch (headless=True ZORUNLU, parametre yok)
   - random.choice ile UA + viewport sec
   - Context: user_agent, viewport, locale=f"{language}-{language.upper()}", timezone_id (TR icin "Europe/Istanbul", default "UTC")
   - playwright_stealth.stealth_async(page) page olusturulduktan sonra cagrilacak — sadece import ve helper hazirla, page olusumunu caller yapsin (ya da context'ten yeni sayfa acan helper fonksiyon)
   - proxy_url verilirse launch'a proxy={"server": proxy_url} gec

5. async detect_captcha(page: Page) -> bool
   - Asagidakilerden herhangi biri varsa True:
     - 'iframe[src*="recaptcha"]'
     - 'div#captcha-form'
     - text="unusual traffic from your computer network" (case-insensitive)
   - 1 saniye timeout, yoksa False

6. async dismiss_consent(page: Page) -> None
   - Maps consent dialog'u: 'button[aria-label*="Reddet"]', 'button[aria-label*="Reject"]', 'button:has-text("Tümünü reddet")', 'button:has-text("Reject all")'
   - Bulursa tikla, yoksa sessizce gec.
   - 3 saniye timeout.

KISITLAR:
- Scrapling import etme. Tamamen playwright.async_api + playwright_stealth.
- requirements.txt'i HENUZ guncellemeyin (Faz 3'te yapilacak), simdilik importlar kalsin.
- Tests: tests/unit/test_browser.py — UA_POOL ve CHROMIUM_ARGS sabit kontroller (pure function testleri, browser launch testi YOK — entegrasyonda yapilir).
````

**Review:** `git diff`, dosya sayisi 4. Commit: `feat(places): add stealth browser launcher`

---

### Faz 1C — Google Maps Engine

**Cursor Prompt:**

````
@docs/places-google-maps-plan.md @Google-Maps-Scrapper/main.py @src/engine/places/browser.py @src/lib/cache.py @src/schemas/places.py

Olustur: src/engine/places/google_maps.py

Bu dosya, ../Google-Maps-Scrapper/main.py'deki XPath'leri ve scroll/click logic'ini async + headless + stealth versiyona port eder.

Fonksiyonlar:

1. _build_search_url(query: str, language: str, region: str | None) -> str
   - Pattern: https://www.google.com/maps/search/{quoted query}/?hl={language}
   - region varsa &gl={region} ekle
   - urllib.parse.quote_plus kullan

2. _parse_coordinates(place_url: str | None) -> Coordinates | None
   - Regex: r"/@(-?\d+\.\d+),(-?\d+\.\d+)"
   - Bulamazsa None

3. async _scroll_until_enough(page: Page, target: int, scroll_panel_selector: str) -> int
   - Maps left panel selector: 'div[role="feed"]'
   - target'a ulasilana veya yeni eleman gelmemeye kadar dongu
   - Her scroll arasi await page.wait_for_timeout(random.randint(800, 1800))
   - Max 30 iterasyon (sonsuz dongu garantisi)
   - Donus: bulunan listing sayisi

4. async _extract_place(page: Page) -> Place | None
   - main.py'deki XPath'leri kullan (name, address, website, phone, reviews_count, reviews_average, place_type, opens_at, introduction)
   - Eklemeler:
     - place_url = page.url (place tikladiktan sonra URL degisir, yakala)
     - coordinates = _parse_coordinates(place_url)
   - name yoksa None don (skip sinyali)
   - Tum extract_text helper'larini bu dosyaya kopyala (paylasilan kutuphane gerekmez)

5. async _search_places_uncached(req: GoogleMapsSearchRequest, proxy_url: str | None) -> GoogleMapsSearchResponse
   - launch_stealth_context cagir
   - new_page + stealth_async
   - page.goto(_build_search_url(...), timeout=req.options.timeout * 1000)
   - dismiss_consent
   - if await detect_captcha(page): return failed response with error="captcha_detected"
   - page.wait_for_selector('a[href*="/maps/place/"]', timeout=15000)
   - _scroll_until_enough(page, req.total)
   - Listing'leri topla: page.locator('a[href*="/maps/place/"]').all()
     - Dedupe by href
     - Slice [:req.total]
   - Her listing icin try/except:
     - listing.click()
     - page.wait_for_selector('h1.DUwDvf', timeout=10000)
     - random sleep 1200-2500ms
     - place = await _extract_place(page)
     - if place and place.name: append
     - Hata: log + skip (job basarisiz olmasin)
   - finally: browser.close()
   - GoogleMapsSearchResponse build et (success=True, duration_ms, cache_hit=False, places=...)

6. async search_places(req: GoogleMapsSearchRequest, redis: Redis, *, cache_bypass: bool = False, proxy_url: str | None = None) -> GoogleMapsSearchResponse
   - cache_key = "places:gmaps:" + sha256(json.dumps({query, total, language, region}, sort_keys=True))
   - cache_bypass False ise redis'ten oku (TTL kontrolu Redis tarafinda); varsa cache_hit=True ile don
   - Yoksa _search_places_uncached cagir
   - Sonucu redis.set ile yaz, ex=21600 (6 saat)
   - Don

KISITLAR:
- src/lib/cache.py'a dokunma; places kendi cache helper'ini bu dosya icinde tutsun (build_cache_key zaten ScrapeRequest'e bagli, yeniden kullanma).
- pandas, csv, dataclass YOK. Sadece pydantic Place modelini kullan.
- print yok, logging.getLogger(__name__) kullan.
- tests/unit/test_places_engine.py:
  - _build_search_url 4 farkli kombinasyon
  - _parse_coordinates 3 case (var, yok, malformed)
  - HTML fixture testi: tests/fixtures/maps_place_panel.html (statik dosya), beautifulsoup ile DOM parse — XPath'lerin patterni dogru mu (browser olmadan basit selector mantik testi).
````

**Review:**
- `git diff --stat`
- `pytest tests/unit/test_places_engine.py -v`
- Commit: `feat(places): add google maps async search engine`

---

### Faz 2A — Sync Route

**Cursor Prompt:**

````
@docs/places-google-maps-plan.md @src/routes/scrape.py @src/engine/places/google_maps.py @src/lib/quota.py @src/config.py

Olustur: src/routes/places.py

Mevcut src/routes/scrape.py PATTERN'ini birebir taklit et:

```python
router = APIRouter(prefix="/api/v1", tags=["places"])

@router.post("/places/google-maps", response_model=GoogleMapsSearchResponse)
async def google_maps_search(
    payload: GoogleMapsSearchRequest,
    request: Request,
    principal: ApiPrincipal = Depends(require_api_key),
    redis: Redis = Depends(get_redis),
) -> GoogleMapsSearchResponse:
    # 1. Rate limit (mevcut)
    await enforce_rate_limit(redis, principal.key_hash)

    # 2. Sync endpoint icin ek koruma: total > 10 ise 400 don, "use jobs endpoint" mesaji
    if payload.total > 10:
        raise HTTPException(400, detail="total_exceeds_sync_limit_use_jobs_endpoint")

    # 3. Daily quota
    settings = get_settings()
    await enforce_daily_quota(redis, principal.key_hash, "places", settings.places_daily_quota)

    # 4. Cache bypass
    cache_bypass = request.headers.get("cache-control", "").lower() == "no-cache"

    # 5. Engine
    return await search_places(payload, redis, cache_bypass=cache_bypass, proxy_url=settings.places_proxy_url or None)
```

src/config.py'a EK alanlar (mevcut alanlara dokunma, sona ekle):
- places_daily_quota: int = Field(default=200, alias="PLACES_DAILY_QUOTA")
- places_proxy_url: str = Field(default="", alias="PLACES_PROXY_URL")

src/main.py'a TEK satir ekle:
- from src.routes.places import router as places_router
- app.include_router(places_router)

Tests:
- tests/integration/test_places_route.py:
  - search_places mock'lanir (monkeypatch)
  - Auth yoksa 401
  - Quota asilirsa 429
  - total=15 -> 400
  - total=5, success=True
  - cache-control: no-cache header forward edilir mi (mock spy)
````

**Review:** Smoke endpoint (`curl` veya HTTPie) ile localhost test. Commit: `feat(places): add sync route /api/v1/places/google-maps`

---

### Faz 2B — Async Job & Worker

**Cursor Prompt:**

````
@docs/places-google-maps-plan.md @src/workers/tasks.py @src/routes/jobs.py @src/engine/places/google_maps.py @src/schemas/job.py

1. Olustur: src/workers/places_tasks.py

src/workers/tasks.py icindeki run_scrape_job DESENINI birebir kopyala, su farklarla:
- Fonksiyon adi: run_places_job
- Import: search_places, GoogleMapsSearchRequest
- payload validasyonu GoogleMapsSearchRequest ile
- Engine cagrisi: search_places(req, redis, proxy_url=get_settings().places_proxy_url or None)
- Quota DUSURME burada: worker icinde de enforce_daily_quota (queued anda dusurmedik mi? — DUSURMEDIK, sadece sync'te dusurduk; jobs/places-google-maps create eden route'a da quota check eklenecek — asagi bak)
- Geri kalan: status update + webhook callback ayni

2. src/workers/tasks.py icine WorkerSettings sinifina TEK satir ek:
   - functions = [run_scrape_job, run_places_job]
   - Yeni import: from src.workers.places_tasks import run_places_job

3. src/schemas/job.py icindeki JobCreateRequest.type literal'ini genislet:
   - type: Literal["scrape", "spider", "places-google-maps"] = "scrape"

4. src/routes/jobs.py icindeki create_job fonksiyonunu degistir:
   MEVCUT:
   ```python
   if payload.type != "scrape":
       raise HTTPException(400, detail="spider_jobs_not_implemented_yet")
   scrape_payload = ScrapeRequest.model_validate(payload.payload).model_dump(...)
   ...
   await pool.enqueue_job("run_scrape_job", job_id, scrape_payload, ...)
   ```

   YENI:
   ```python
   if payload.type == "scrape":
       job_payload = ScrapeRequest.model_validate(payload.payload).model_dump(mode="json")
       function_name = "run_scrape_job"
   elif payload.type == "places-google-maps":
       await enforce_daily_quota(redis, principal.key_hash, "places", get_settings().places_daily_quota)
       job_payload = GoogleMapsSearchRequest.model_validate(payload.payload).model_dump(mode="json")
       function_name = "run_places_job"
   else:
       raise HTTPException(400, detail="unsupported_job_type")
   ...
   await pool.enqueue_job(function_name, job_id, job_payload, ...)
   ```

KISITLAR:
- Mevcut "scrape" davranisi DEGISMEYECEK; sadece if/elif ile genisletildi.
- run_scrape_job'a, post_callback'e, webhook'a dokunma.

5. tests/integration/test_places_job.py:
   - "places-google-maps" type ile POST /api/v1/jobs -> 202
   - "scrape" type hala calisir (regression)
   - "spider" -> 400
   - Quota asilirsa 429
   - Mock arq pool (enqueue_job spy)
````

**Review:**
- `pytest tests/ -v` (tum testler)
- Commit: `feat(places): add async job type places-google-maps`

---

### Faz 3 — Bagimlilik & Docker

**Cursor Prompt:**

````
@docs/places-google-maps-plan.md @requirements.txt @Dockerfile @docker-compose.yml @docker-compose.prod.yml @.env.example

1. requirements.txt'e ekle (alfabetik degil, mevcut sirayi koru, sona ekle):
   playwright>=1.44.0,<2.0.0
   playwright-stealth>=1.0.6

2. Dockerfile'i guncelle:
   - Mevcut FROM pyd4vinci/scrapling base'i koru.
   - pip install sonrasina ekle:
     RUN python -m playwright install chromium --with-deps || python -m playwright install chromium
   - shm_size icin not (compose'da set edilecek).

3. docker-compose.yml ve docker-compose.prod.yml:
   - scraper-service ve worker (varsa) servislerine:
     shm_size: 1gb
   - environment'a ekle:
     PLACES_DAILY_QUOTA: ${PLACES_DAILY_QUOTA:-200}
     PLACES_PROXY_URL: ${PLACES_PROXY_URL:-}

4. .env.example'a ekle:
   PLACES_DAILY_QUOTA=200
   PLACES_PROXY_URL=

5. README.md'ye 1 paragraf compliance uyarisi (en alta "Places Provider" basligi):
   "POST /api/v1/places/google-maps Google Maps'ten kamuya acik isletme verisi cikarir.
   Sadece kendi sahip oldugunuz veya yetkili oldugunuz veri toplama amaclariniz icin kullanin.
   Google Maps Terms of Service'i okumak ve uymak kullanicinin sorumlulugundadir.
   Servis CAPTCHA ile karsilasirsa istek otomatik basarisiz dondurur."

KISITLAR:
- pyproject.toml'a dokunma (zaten requirements.txt ile yonetiliyor).
- mevcut env degiskenlerini DEGISTIRME, sadece ekle.
````

**Review:**
- `docker compose build scraper-service` (lokal)
- `docker compose up -d`
- Smoke: `curl -s http://localhost:8200/` -> ok
- Commit: `chore(places): add playwright deps and docker shm config`

---

### Faz 4 — Dokumantasyon

**Cursor Prompt:**

````
@docs/api.md @docs/client-integration.md

1. docs/api.md sonuna yeni bolum:

## POST /api/v1/places/google-maps (Sync)

### Request
```json
{
  "query": "diş hekimi konya",
  "total": 5,
  "language": "tr",
  "region": "tr"
}
```

- total maksimum 10 (sync icin). Daha buyuk total icin /api/v1/jobs kullan.
- Daily quota: PLACES_DAILY_QUOTA (default 200).

### Response
[plan dosyasindaki ornegi koy — 4. Bolum]

## POST /api/v1/jobs (type=places-google-maps)
```json
{
  "type": "places-google-maps",
  "payload": {
    "query": "kuyumcu kayseri",
    "total": 50,
    "language": "tr"
  },
  "callback_url": "https://example.com/api/scraper/callback",
  "callback_secret": "min8char_secret"
}
```

Response: standart JobCreateResponse. Sonuc /api/v1/jobs/{job_id} ile poll edilir veya callback'e gonderilir.

2. docs/client-integration.md sonuna ek:

## Places (Google Maps)

### Sync
[TypeScript ornek — fetch ile]

### Async
[TypeScript ornek — job create + poll]

### Callback
[Webhook signature dogrulama ornegi]
````

Ornek kodlar icin: `docs/places-usage-guide.md` ayrica yazilacak (asagida ayri talimat).

**Commit:** `docs(places): document google maps endpoint`

---

### Faz 5 — Manuel Smoke

```bash
# Lokal
docker compose up -d
curl -X POST http://localhost:8200/api/v1/places/google-maps \
  -H "Authorization: Bearer scraper-test-localdev" \
  -H "Content-Type: application/json" \
  -d '{"query": "kahveci konya", "total": 3, "language": "tr"}'

# Beklenen: ~15-25sn icinde 3 places
```

CAPTCHA testi:
```bash
# Hizli pespese 5 istek at, son istekte error="captcha_detected" donmeli
for i in 1 2 3 4 5; do
  curl -X POST ... -d '{"query": "test '$i'", "total": 5}' &
done
wait
```

---

## 2. Cursor Best Practices (Bu Proje Icin)

### Composer vs Chat
- **Composer**: Cok dosyali degisikliklerde (Faz 1A, 1B, 1C, 2A, 2B). Plan + asagidaki prompt birlikte.
- **Chat**: Tek dosya degisikligi, dogrulama, soru-cevap.

### Context Yonetimi
- Her faz prompt'unda **sadece ilgili dosyalari** `@` ile context'e ekle.
- Tum repo'yu `@` ile cekme — context overflow + plan disi onerilere yol acar.
- Plan dosyasi (`@docs/places-google-maps-plan.md`) HER prompt'a ekli olmali.

### Acceptance Loop
1. Cursor diff onerir.
2. Cursor'da **Apply** etmeden once diff'i oku.
3. **Apply** sonrasi `git diff`'i terminalde tekrar gozden gecir.
4. Test calistir (`pytest`).
5. Yesil ise commit, kirmizi ise Cursor'a hata mesajini geri ver, fix iste.

### Hallucination Onleme
- Cursor "playwright_stealth" yerine "selenium-stealth" gibi yanlis paket onerirse: **reject + dogru paket adi ile geri don**.
- "scrapling.fetchers'i kullanalim" derse: **reject** (plan kararina aykiri).
- Mevcut dosyalarda "iyilestirme" onerirse (refactor, type fix vb.): **reject** (scope dışı, ayri PR).

### Commit Discipline
- Her faz = 1 commit. Squash YAPMA, history korunsun.
- Conventional commit: `feat(places): ...`, `chore(places): ...`, `docs(places): ...`, `test(places): ...`

---

## 3. Cursor Bittikten Sonra Claude Code Review

Cursor tum fazlari bitirdiginde:

```bash
git log --oneline feat/places-google-maps ^main
git diff main..feat/places-google-maps --stat
```

Sonra Claude Code'a su prompt'u ver:

> @docs/places-google-maps-plan.md @docs/places-cursor-implementation.md
>
> Cursor feat/places-google-maps branch'ini implement etti. Diff'i incele:
> - Plan dosyasindaki kisitlar ihlal edilmis mi?
> - Mevcut scrape akisi degisti mi (regression riski)?
> - Anti-bot kurallari (headless, retry yok, CAPTCHA detect, quota) eksiksiz mi?
> - Test coverage yeterli mi?
> - Production'a aciksak ne risk gorursun?

Onay aldiktan sonra Antigravity'ye gercek arama dogrulamasi.
