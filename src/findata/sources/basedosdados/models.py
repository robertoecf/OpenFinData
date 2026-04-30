"""Models for Base dos Dados integration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AccessMode = Literal["free_public", "free_logged_in", "paid_logged_in"]


class AccessPath(BaseModel):
    """One way to access Base dos Dados."""

    name: str
    access: AccessMode
    description: str
    requires: list[str] = Field(default_factory=list)


class BaseDosDadosInfo(BaseModel):
    """Static source descriptor for Base dos Dados."""

    source: str
    status: str
    homepage: str
    docs: str
    access_paths: list[AccessPath]
    notes: list[str]


class BigQueryTableRef(BaseModel):
    """Reference to a public Base dos Dados BigQuery table."""

    dataset_id: str
    table_id: str
    full_table_id: str
    access: AccessMode = "free_logged_in"
    sql: str


class QueryPreview(BaseModel):
    """Small local SQL preview result from the optional basedosdados SDK."""

    query: str
    rows: list[dict[str, Any]]
    row_count: int
    access: AccessMode = "free_logged_in"
