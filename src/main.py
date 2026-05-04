from fastapi import FastAPI

from src.config import get_settings
from src.routes.health import router as health_router
from src.routes.jobs import router as jobs_router
from src.routes.places import router as places_router
from src.routes.scrape import router as scrape_router

settings = get_settings()

app = FastAPI(
    title="Scraper Service",
    description="Central Scrapling-powered scraping service.",
    version="0.2.0",
)

app.include_router(health_router)
app.include_router(scrape_router)
app.include_router(places_router)
app.include_router(jobs_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "ok"}
