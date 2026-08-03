"""Pydantic schemas shared across routers.

Every response leaves the API wrapped in :class:`Envelope`, so clients can rely on a
single shape whether a call succeeded or failed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class Envelope(BaseModel, Generic[T]):
    data: T | None = None
    error: ErrorDetail | None = None
    meta: Meta = Field(default_factory=Meta)


class HealthStatus(BaseModel):
    status: str
    version: str


class ReadyStatus(BaseModel):
    db: str
