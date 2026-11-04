from datetime import datetime

from pydantic import BaseModel, Field


class WebsiteSourceCreate(BaseModel):
    url: str = Field(min_length=9, max_length=2048)
    refresh_interval_hours: int = Field(default=24, ge=1, le=720)
    max_pages: int = Field(default=50, ge=1, le=100)
    available_to_all_agents: bool = True


class WebsiteSourceResponse(BaseModel):
    source_uuid: str
    url: str
    status: str
    is_active: bool
    available_to_all_agents: bool
    refresh_interval_hours: int
    max_pages: int
    last_refresh_started_at: datetime | None
    last_refreshed_at: datetime | None
    next_refresh_at: datetime | None
    last_error: str | None
    etag: str | None
    content_hash: str | None
    version: int
    document_uuid: str | None = None


class WebsiteSourceList(BaseModel):
    sources: list[WebsiteSourceResponse]
