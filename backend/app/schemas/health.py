"""Pydantic schemas for health/status endpoints."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app_name: str
    app_env: str


class RootResponse(BaseModel):
    message: str
    docs_url: str
