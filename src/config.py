from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="scraper-service", alias="APP_NAME")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8200, alias="API_PORT")
    api_keys: str = Field(default="", alias="API_KEYS")
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    cache_ttl_seconds: int = Field(default=86_400, alias="CACHE_TTL_SECONDS")
    default_timeout_seconds: int = Field(default=30, alias="DEFAULT_TIMEOUT_SECONDS")
    default_rate_limit_per_minute: int = Field(default=60, alias="DEFAULT_RATE_LIMIT_PER_MINUTE")
    max_concurrent_browsers: int = Field(default=2, alias="MAX_CONCURRENT_BROWSERS")
    browser_close_timeout_seconds: int = Field(default=20, alias="BROWSER_CLOSE_TIMEOUT_SECONDS")
    reaper_max_age_seconds: int = Field(default=900, alias="REAPER_MAX_AGE_SECONDS")
    reaper_interval_seconds: int = Field(default=600, alias="REAPER_INTERVAL_SECONDS")
    log_level: str = Field(default="info", alias="LOG_LEVEL")
    places_daily_quota: int = Field(default=200, alias="PLACES_DAILY_QUOTA")
    places_proxy_url: str = Field(default="", alias="PLACES_PROXY_URL")
    lead_daily_quota: int = Field(default=500, alias="LEAD_DAILY_QUOTA")
    directory_daily_quota: int = Field(default=200, alias="DIRECTORY_DAILY_QUOTA")
    fair_daily_quota: int = Field(default=100, alias="FAIR_DAILY_QUOTA")
    fair_proxy_url: str = Field(default="", alias="FAIR_PROXY_URL")

    @property
    def api_key_set(self) -> set[str]:
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
