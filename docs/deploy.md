# Deploy

## Manual Prerequisites

1. DNS: `scraper.guezelwebdesign.com` A record points to `72.61.93.212`.
2. Docker and Docker Compose v2 are installed on the VPS.
3. Initial Let's Encrypt certificate exists at `/etc/letsencrypt/live/scraper.guezelwebdesign.com/` or is mounted into the `letsencrypt-certs` volume.

## First Install

```bash
sudo mkdir -p /var/www/scraper-service
cd /var/www/scraper-service
git clone <repo-url> .
cp .env.example .env
python3 scripts/generate-api-key.py geoserra
# Put the generated key into API_KEYS in .env and into GeoSerra SCRAPER_API_KEY.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Health Check

```bash
curl http://127.0.0.1:8200/health
curl https://scraper.guezelwebdesign.com/health
```

## Redeploy

```bash
APP_DIR=/var/www/scraper-service ./scripts/deploy.sh
```

## SSL Note

For the first certificate, stop anything on ports 80/443 and run certbot standalone manually, or mount an existing host-managed certificate into the `letsencrypt-certs` Docker volume. After that, webroot renewal can use `certbot-webroot`.
