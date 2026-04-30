"""Base dos Dados — free logged-in access via SQL, Python and R."""

from findata.sources.basedosdados.catalog import (
    PYTHON_DOCS_URL,
    BaseDosDadosSDKNotInstalledError,
    get_columns,
    get_datasets,
    get_tables,
    read_sql_preview,
    resolve_billing_project_id,
    search_datasets,
    search_direct_download_free,
    source_info,
    table_ref,
)
from findata.sources.basedosdados.models import (
    AccessMode,
    AccessPath,
    BaseDosDadosInfo,
    BigQueryTableRef,
    QueryPreview,
)

__all__ = [
    "PYTHON_DOCS_URL",
    "AccessMode",
    "AccessPath",
    "BaseDosDadosInfo",
    "BaseDosDadosSDKNotInstalledError",
    "BigQueryTableRef",
    "QueryPreview",
    "get_columns",
    "get_datasets",
    "get_tables",
    "read_sql_preview",
    "resolve_billing_project_id",
    "search_datasets",
    "search_direct_download_free",
    "source_info",
    "table_ref",
]
