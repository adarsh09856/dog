"""Public-safe platform identity, shared by owner and client settings."""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class PlatformBranding(BaseModel):
    company_name: str = Field(default="Kodewaves", min_length=1, max_length=80)
    tagline: str = Field(default="Voice agents for web and phone", max_length=160)
    logo_url: str = Field(default="", max_length=500)
    favicon_url: str = Field(default="/kodewaves-mark.svg", max_length=500)
    support_email: str = Field(default="", max_length=254)
    primary_color: str = "#304c73"
    font: Literal["geist", "system"] = "geist"

    @field_validator("company_name", "tagline")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned and value != "":
            raise ValueError("Brand text cannot contain only whitespace")
        return cleaned

    @field_validator("primary_color")
    @classmethod
    def valid_color(cls, value: str) -> str:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Primary color must be a six-digit hex color")
        return value.lower()

    @field_validator("logo_url", mode="before")
    @classmethod
    def normalize_legacy_logo(cls, value: str) -> str:
        # This was the platform seed default, but no /logo.png is shipped.
        # Empty tells BrandLogo to render its current inline Kodewaves mark.
        return "" if value == "/logo.png" else value

    @field_validator("favicon_url", mode="before")
    @classmethod
    def normalize_legacy_favicon(cls, value: str) -> str:
        # Existing installs retain this seeded value in the database.
        return "/kodewaves-mark.svg" if value in (None, "", "/favicon.ico") else value

    @field_validator("logo_url", "favicon_url")
    @classmethod
    def valid_image_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if value.startswith("/") and not value.startswith("//") and "\\" not in value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Image URL must be a site path or HTTPS URL")
        return value

    @field_validator("support_email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip()
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid support email")
        return value
