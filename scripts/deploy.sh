#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/var/www/scraper-service}
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

cd "$APP_DIR"

git pull --ff-only
$COMPOSE build
$COMPOSE up -d
$COMPOSE ps
curl -fsS http://127.0.0.1:8200/health || true
