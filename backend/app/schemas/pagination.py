"""Pagination contract (API-03: every list endpoint is paginated).

Convention (documented in docs/api-contract.md):
- List endpoints accept ``limit`` (default 20, max 100) and ``offset`` (>= 0).
- List responses are the envelope ``{"items": [...], "total": N, ...}``
  where ``total`` counts all rows matching the filters (not just the page).
"""
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

#: Hard cap on one page (contract §conventions; bounded per batch 2026-11-07).
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class PaginationParams(BaseModel):
    """Query parameters shared by every list endpoint (API-03).

    Used as a FastAPI dependency: each field becomes a query parameter.
    """

    model_config = ConfigDict(extra="ignore")

    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)


class Page(BaseModel, Generic[T]):
    """The list response envelope. `total` = filtered row count (API-03)."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(ge=0)
