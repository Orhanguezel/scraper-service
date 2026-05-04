#!/usr/bin/env bash
# Places (Google Maps) smoke checks — lokal veya production.
# Kullanim:
#   ./scripts/places-smoke.sh                    # SCRAPER_URL=http://127.0.0.1:8200
#   SCRAPER_URL=https://scraper.guezelwebdesign.com SCRAPER_API_KEY='Bearer ...' ./scripts/places-smoke.sh
set -euo pipefail

BASE_URL="${SCRAPER_URL:-http://127.0.0.1:8200}"
BASE_URL="${BASE_URL%/}"
KEY_HEADER="${SCRAPER_API_KEY:-}"

if [[ -z "$KEY_HEADER" ]]; then
  echo "WARN: SCRAPER_API_KEY bos; sadece / ve /health denenir (places 401 beklenir)." >&2
  AUTH=()
else
  if [[ "$KEY_HEADER" != Bearer* ]]; then
    KEY_HEADER="Bearer ${KEY_HEADER#Bearer }"
  fi
  AUTH=(-H "Authorization: ${KEY_HEADER}")
fi

echo "== Base: ${BASE_URL}"
curl -fsS "${BASE_URL}/" | head -c 200 || true
echo
curl -fsS "${BASE_URL}/health" || { echo "FAIL: health"; exit 1; }
echo " OK health"

if ((${#AUTH[@]})); then
  echo "== POST /api/v1/places/google-maps (sync, total=2, ~20-60sn surer)..."
  curl -fsS -X POST "${BASE_URL}/api/v1/places/google-maps" \
    "${AUTH[@]}" \
    -H "Content-Type: application/json" \
    -d '{"query":"eczane konya","total":2,"language":"tr","region":"tr"}' \
    | head -c 1200
  echo
  echo "OK places sync tamamlandi (cikti kesildi)."
else
  echo "== Places atlandi (SCRAPER_API_KEY yok)."
fi
