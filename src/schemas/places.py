from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlacesOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout: int = Field(default=60, ge=1, le=180)


class GoogleMapsSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=200)
    total: int = Field(default=20, ge=1, le=120)
    language: str = Field(default="tr", pattern=r"^[a-z]{2}$")
    region: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    options: PlacesOptions = Field(default_factory=PlacesOptions)


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float
    lng: float


class Place(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    address: str | None = None
    website: str | None = None
    phone: str | None = None
    place_type: str | None = None
    opens_at: str | None = None
    introduction: str | None = None
    reviews_count: int | None = None
    reviews_average: float | None = None
    place_url: str | None = None
    coordinates: Coordinates | None = None


class GoogleMapsSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    query: str
    total_found: int
    duration_ms: int
    cache_hit: bool
    fetched_at: datetime
    places: list[Place] = Field(default_factory=list)
    error: str | None = None
