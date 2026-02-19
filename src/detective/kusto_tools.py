"""Kusto query, command, and exploration tools for the detective agent."""

import json
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from copilot import define_tool
from pydantic import BaseModel, Field

_clients: dict[str, KustoClient] = {}
_cache_path: Path | None = None


def set_cache_path(path: Path) -> None:
    """Set the per-session Kusto cache file path."""
    global _cache_path
    _cache_path = path


def _get_client(cluster_uri: str) -> KustoClient:
    """Get or create a cached KustoClient for a cluster."""
    if cluster_uri not in _clients:
        credential = DefaultAzureCredential()
        kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
            cluster_uri, credential
        )
        _clients[cluster_uri] = KustoClient(kcsb)
    return _clients[cluster_uri]


def _result_to_str(result) -> str:
    """Convert a Kusto result set to a readable string."""
    rows = []
    for table in result.primary_results:
        columns = [col.column_name for col in table.columns]
        rows.append(" | ".join(columns))
        rows.append("-" * len(rows[-1]))
        for row in table:
            rows.append(" | ".join(str(row[col]) for col in columns))
    if not rows:
        return "(empty result)"
    return "\n".join(rows)


def _load_cache() -> dict:
    if _cache_path is not None and _cache_path.exists():
        return json.loads(_cache_path.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    if _cache_path is None:
        return
    _cache_path.parent.mkdir(parents=True, exist_ok=True)
    _cache_path.write_text(json.dumps(cache, indent=2, default=str), encoding="utf-8")


# --- Exploration tool with caching ---


class KustoExploreParams(BaseModel):
    cluster_uri: str = Field(description="The Kusto cluster URI")
    database: str = Field(description="The database name to explore")


@define_tool(
    description=(
        "Explore a Kusto database: list tables, their schemas, row counts, "
        "and sample rows. Results are cached — subsequent calls return "
        "instantly without querying the cluster. Use this FIRST before "
        "writing any KQL queries."
    )
)
def kusto_explore(params: KustoExploreParams) -> str:
    cache_key = f"{params.cluster_uri}|{params.database}"
    cache = _load_cache()

    if cache_key in cache:
        return _format_cache_entry(cache[cache_key])

    # Fetch fresh
    client = _get_client(params.cluster_uri)
    entry: dict = {"tables": {}}

    try:
        # Get table list
        tables_result = client.execute_mgmt(params.database, ".show tables")
        table_names = []
        for table in tables_result.primary_results:
            for row in table:
                name = str(row["TableName"])
                table_names.append(name)

        # For each table: schema, count, sample
        for tname in table_names:
            tinfo: dict = {}
            try:
                schema_result = client.execute(
                    params.database, f"{tname} | getschema"
                )
                cols = []
                for t in schema_result.primary_results:
                    for row in t:
                        cols.append(
                            f"{row['ColumnName']}:{row['ColumnType']}"
                        )
                tinfo["schema"] = cols
            except Exception:
                tinfo["schema"] = []

            try:
                count_result = client.execute(
                    params.database, f"{tname} | count"
                )
                for t in count_result.primary_results:
                    for row in t:
                        tinfo["count"] = int(row["Count"])
            except Exception:
                tinfo["count"] = -1

            try:
                sample_result = client.execute(
                    params.database, f"{tname} | take 3"
                )
                tinfo["sample"] = _result_to_str(sample_result)[:1000]
            except Exception:
                tinfo["sample"] = ""

            entry["tables"][tname] = tinfo

        cache[cache_key] = entry
        _save_cache(cache)
        output = _format_cache_entry(entry)
    except Exception as e:
        output = f"Explore error: {e}"

    return output


def _format_cache_entry(entry: dict) -> str:
    lines = []
    for tname, tinfo in entry.get("tables", {}).items():
        count = tinfo.get("count", "?")
        schema = ", ".join(tinfo.get("schema", []))
        lines.append(f"## {tname} ({count} rows)")
        lines.append(f"Schema: {schema}")
        sample = tinfo.get("sample", "")
        if sample:
            lines.append(f"Sample:\n{sample}")
        lines.append("")
    return "\n".join(lines) if lines else "(no tables found)"


# --- Query and command tools (unchanged) ---


class KustoQueryParams(BaseModel):
    cluster_uri: str = Field(
        description="The Kusto cluster URI, e.g. https://help.kusto.windows.net"
    )
    database: str = Field(description="The database name to query")
    query: str = Field(description="The KQL query to execute")


@define_tool(description="Execute a KQL query against a Kusto cluster and return results.")
def kusto_query(params: KustoQueryParams) -> str:
    client = _get_client(params.cluster_uri)
    try:
        result = client.execute(params.database, params.query)
        output = _result_to_str(result)
    except Exception as e:
        output = f"Query error: {e}"

    return output


class KustoCommandParams(BaseModel):
    cluster_uri: str = Field(description="The Kusto cluster URI")
    database: str = Field(description="The database name")
    command: str = Field(description="The management command to execute (e.g. .show tables)")


KUSTO_COMMAND_DESC = "Execute a Kusto management command (e.g. .show tables, .show table schema)"


@define_tool(description=KUSTO_COMMAND_DESC)
def kusto_command(params: KustoCommandParams) -> str:
    client = _get_client(params.cluster_uri)
    try:
        result = client.execute_mgmt(params.database, params.command)
        output = _result_to_str(result)
    except Exception as e:
        output = f"Command error: {e}"

    return output
