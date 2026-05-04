from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from src.schemas.scrape import ScrapeRequest, ScrapeResponse


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class JobCreateRequest(BaseModel):
    type: Literal["scrape", "spider", "places-google-maps"] = "scrape"
    payload: dict[str, Any]
    callback_url: HttpUrl | None = None
    callback_secret: str | None = Field(default=None, min_length=8)


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    poll_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    type: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    result: Any | None = None
    error: str | None = None
