#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/var/www/scraper-service}
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

cd "$APP_DIR"

git pull --ff-only
$COMPOSE build

# Host'ta zaten 80/443 nginx varsa compose icindeki nginx port cakismasi yapar.
# .env icine SKIP_COMPOSE_NGINX=1 yaz: sadece api + worker + redis kalir (trafigi host nginx 8200'e proxy'ler).
if [[ -f .env ]] && grep -qE '^[[:space:]]*SKIP_COMPOSE_NGINX=1[[:space:]]*$' .env; then
  $COMPOSE up -d api worker redis
else
  $COMPOSE up -d
fi
$COMPOSE ps
curl -fsS http://127.0.0.1:8200/health || true
