# Scraper-Service — Lead Machine Entegrasyon Çeklistesi

> Durum: 2026-05-07
> Bağlam: MarketPulse `scraper.client.ts`, bu servisi Lead Machine'in scraping motoru olarak kullanır.
> **Kural:** Bu servise **breaking change girilmez.** Mevcut endpoint'ler (`/scrape`, `/places/google-maps`, `/jobs`) korunur.
> Sadece yeni profiller ve yeni job type'ı eklenir.

---

## Mevcut Durum (Dokunulmayacak)

| Özellik | Durum |
|---------|-------|
| `POST /api/v1/scrape` (profil: `geo-page`, `geo-robots`) | ✅ Production'da çalışıyor |
| `POST /api/v1/places/google-maps` (sync, ≤10) | ✅ Production'da çalışıyor |
| `POST /api/v1/jobs` (type: `scrape`, `places-google-maps`) | ✅ Production'da çalışıyor |
| `GET /api/v1/jobs/{job_id}` | ✅ Production'da çalışıyor |
| Redis cache (6s TTL places, 24h scrape) | ✅ |
| arq job queue + webhook callback (HMAC-SHA256) | ✅ |

---

## BÖLÜM A — Yeni Scrape Profilleri

> **Öncelik:** 🔴 Kritik — MarketPulse Lead Machine'in çalışması için gerekli
> **Kural:** `ScrapeProfile` tipi `scraper.client.ts`'de güncellendi; servis `profile` değerini tanımıyorsa `data: {}` döner — bu acceptable fallback.

### A1. `lead-page` / `website-analysis` profili

> **Amaç:** Şirket web sitesini B2B lead sinyalleri açısından analiz et.

- [x] `src/engine/extractors.py`'e `extract_lead_page(html, url, response)` fonksiyonu ekle:
  ```python
  def extract_lead_page(html: str, url: str, response: Any) -> dict[str, Any]:
      """
      Döndürür:
        title, description, text_content (max 8000 karakter)
        has_b2b_signals: bool  (wholesale, distributor, importer, bayi, toptan)
        has_china_signals: bool (china, çin, made in china)
        has_private_label: bool (private label, özel marka, white label)
        contact_emails: list[str]  (plaintext email regex)
        contact_phones: list[str]  (tel: link + regex)
        social_profiles: list[{platform, url}]
        firm_type_hints: list[str]  (distributor, importer, wholesaler, retailer, manufacturer)
        product_keywords: list[str]  (h1-h3 + nav link keywords)
      """
  ```

- [x] `src/engine/service.py`'e profil kaydı ekle:
  ```python
  elif payload.profile in ("lead-page", "website-analysis"):
      data = extract_lead_page(fetched.html, str(payload.url), fetched.response)
  ```

- [x] `src/schemas/scrape.py`'de `ScrapeProfile` literal'ine ekle:
  ```python
  ScrapeProfile = Literal["geo-page", "geo-robots", "lead-page", "website-analysis",
                          "directory-listing", "fair-exhibitor", "competitor-page"]
  ```

- [ ] `docs/api.md`'e `lead-page` profil örneği ekle

---

### A2. `directory-listing` profili

> **Amaç:** Europages, Kompass, TOBB gibi B2B dizin sayfalarından firma listesi çıkar.

- [x] `src/engine/extractors.py`'e `extract_directory_listing(html, url, response)` ekle:
  ```python
  def extract_directory_listing(html: str, url: str, response: Any) -> dict[str, Any]:
      """
      Döndürür:
        companies: list[{name, website, country, city, phone, email, description, profile_url}]
        total_found: int
        page_info: {current, total_pages, has_next}
      
      Desteklenen kaynaklar:
        - Europages: .supplier-card, .company-name, .company-country
        - Kompass: .company-item, table.directory-list  
        - TOBB: table#uyeListesi tr
        - Genel fallback: h2/h3 + ul/li + table pattern tespiti
      """
  ```

- [x] `src/engine/service.py`'de profil routing'e ekle

- [ ] Europages anti-bot: `mode=stealthy` ile + `options.solve_cloudflare=true` öner (docs'a not ekle)

---

### A3. `fair-exhibitor` profili

> **Amaç:** Fuar resmi sitesinden exhibitor listesini parse et.

- [x] `src/engine/extractors.py`'e `extract_fair_exhibitor_list(html, url, response)` ekle:
  ```python
  def extract_fair_exhibitor_list(html: str, url: str, response: Any) -> dict[str, Any]:
      """
      Döndürür:
        exhibitors: list[{name, website, country, booth_number, description, hall}]
        fair_name: str | None  (sayfa title veya h1'den)
        total_found: int
      
      Pattern tespiti (öncelik sırasıyla):
        1. JSON-LD (Event > performer/organizer)
        2. table.exhibitor-list, .exhibitor-card, [data-exhibitor]
        3. ul/li pattern (her li'de company ismi)
        4. JSON embed (window.__EXHIBITORS__ = [...])
      """
  ```

- [x] `src/engine/service.py`'de profil routing'e ekle

- [ ] Test fuarı: Automechanika Frankfurt exhibitor list URL ile test yap

---

### A4. `competitor-page` profili

> **Amaç:** Rakip site fiyat/ürün/kampanya değişikliği izleme.

- [x] `src/engine/extractors.py`'e `extract_competitor_page(html, url, response)` ekle:
  ```python
  def extract_competitor_page(html: str, url: str, response: Any) -> dict[str, Any]:
      """
      Döndürür:
        title, description
        prices: list[{text, context, currency_hint}]  (regex: \d+[.,]\d{2}[€$₺£])
        products: list[{name, price, url}]  (product schema + heuristic)
        campaigns: list[str]  (sale/indirim/% off kelimelerinin bulunduğu bloklar)
        content_hash: str  (SHA256 of normalized key fields — change detection için)
        changed_fields: list[str]  (önceki snapshot ile kıyaslama: price, product, campaign)
      """
  ```

- [x] `src/engine/service.py`'de profil routing'e ekle

---

## BÖLÜM B — Yeni Job Type

### B1. `spider` Job Type

> **Amaç:** Çok sayfalı web sitesi tarama (bir URL → tüm iç linkleri tara).
> **Durum:** `job.py`'de `spider` type kabul ediliyor ama `400 unsupported_job_type` döner.

- [x] `src/schemas/job.py`'de tanım zaten var: `type: Literal["scrape", "spider", "places-google-maps"]`
- [x] `src/workers/spider_tasks.py` yeni dosya oluştur:
  ```python
  async def run_spider_job(ctx, job_id, payload, callback_url=None, callback_secret=None):
      """
      payload: { start_url, max_pages=20, profile="lead-page", follow_patterns=[] }
      Her sayfayı sırayla scrape eder, sonuçları birleştirir.
      results: list[{ url, data }]
      """
  ```
- [x] `src/workers/tasks.py`'de `WorkerSettings.functions`'a `run_spider_job` ekle
- [x] `src/routes/jobs.py`'de `spider` case'ini ekle

---

## BÖLÜM C — Config Güncellemeleri

### C1. Yeni Env Değişkenleri

- [x] `.env.example`'a ekle:
  ```
  # Lead Machine için callback security (MarketPulse'dan gelen)
  LEAD_CALLBACK_SECRET=
  
  # Fuar proxy (bazı fuar siteleri geo-block yapar)
  FAIR_PROXY_URL=
  ```

### C2. Rate Limit Ayarları

- [x] `config.py`'e yeni ayarlar:
  ```python
  lead_daily_quota: int = Field(default=500, alias="LEAD_DAILY_QUOTA")
  directory_daily_quota: int = Field(default=200, alias="DIRECTORY_DAILY_QUOTA")
  fair_daily_quota: int = Field(default=100, alias="FAIR_DAILY_QUOTA")
  ```
- [ ] Her yeni profil için `lib/quota.py`'de `enforce_daily_quota(redis, key_hash, "lead", settings.lead_daily_quota)` çağrısı

---

## BÖLÜM D — Test ve Doğrulama

### D1. Profil Unit Testleri

- [ ] `tests/test_lead_page.py`:
  - Gerçek şirket URL'i için `lead-page` profili çalıştır
  - `has_b2b_signals`, `contact_emails`, `firm_type_hints` alanları dolu olmalı

- [ ] `tests/test_directory_listing.py`:
  - Europages örnek URL ile `directory-listing` profili test
  - En az 5 firma döndürmeli

- [ ] `tests/test_fair_exhibitor.py`:
  - Automechanika Frankfurt exhibitor URL ile test
  - En az 10 exhibitor döndürmeli

### D2. Geriye Dönük Uyumluluk

- [ ] Mevcut profiller (`geo-page`, `geo-robots`) hâlâ aynı çıktıyı üretmeli
- [ ] Bilinmeyen profil (`profile="unknown"`) → `data: {}` döner, 200 OK (mevcut davranış korunmalı)

---

## BÖLÜM E — Dokümantasyon

- [ ] `docs/api.md`'e 4 yeni profil için örnek request/response ekle
- [ ] `docs/lead-competitor-architecture.md` referansı: profiller "eklenecek" değil "mevcut" olarak güncelle
- [ ] `docs/client-integration.md`'e `lead-page` ve `directory-listing` TypeScript örneği ekle:
  ```ts
  // Şirket sitesi analizi
  await fetch(`${SCRAPER_URL}/api/v1/scrape`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: 'https://example-distributor.de',
      mode: 'stealthy',
      profile: 'lead-page',
      return_text: true,
    }),
  });
  ```

---

## BÖLÜM F — Dağıtım

> Mevcut Docker compose değişmez. Servis restart yeterli.

- [ ] VPS'te: `docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d --build`
- [ ] Health check: `GET /api/v1/health` → `{ status: "ok" }`
- [ ] Smoke test: `lead-page` profili ile gerçek URL scrape et

---

## Görev Özeti

| Görev | Öncelik | Tahmini Süre | Blok |
|-------|---------|--------------|------|
| A1 — `lead-page`/`website-analysis` profili | 🔴 Kritik | 2-3 saat | — |
| A2 — `directory-listing` profili | 🔴 Kritik | 3-4 saat | — |
| A3 — `fair-exhibitor` profili | 🟡 Yüksek | 2-3 saat | — |
| A4 — `competitor-page` profili | 🟠 Orta | 2-3 saat | — |
| B1 — `spider` job type | 🟠 Orta | 4-6 saat | A1 |
| C1-C2 — Config güncellemeleri | 🟡 Yüksek | 1 saat | — |
| D1-D2 — Testler | 🟡 Yüksek | 2-3 saat | A1-A3 |
| E — Dokümantasyon | 🟢 Düşük | 1 saat | D |
| F — Dağıtım | 🔴 Kritik | 30 dk | tümü |

**Toplam tahmini: 18-26 saat**

---

## MarketPulse ↔ Scraper-Service Etkileşim Özeti

```
MarketPulse backend (scraper.client.ts)
  ├── Sync scrape:   POST /api/v1/scrape   {url, mode, profile, return_text}
  │     Profiller:   lead-page/website-analysis, directory-listing, fair-exhibitor
  │
  ├── Google Maps:   POST /api/v1/places/google-maps   {query, total≤10, language, region}
  │     Already:     ✅ Mevcut — sıfır değişiklik
  │
  ├── Async job:     POST /api/v1/jobs   {type, payload, callback_url, callback_secret}
  │     Callback:    POST /admin/lead-machine/scraper-callback (MarketPulse)
  │     İmza:        X-Scraper-Signature: sha256=<HMAC-SHA256(secret, body)>
  │
  └── Job poll:      GET /api/v1/jobs/{job_id}
```

---

*Scraper-Service — Lead Machine Entegrasyon Çeklistesi*
*2026-05-07*
