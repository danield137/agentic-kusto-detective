"""Set up test data in the Kusto dev cluster for E2E testing.

Creates the TestChallenges database tables and ingests test data.
Idempotent — safe to re-run.

Usage:
    python tests/setup_kusto.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from azure.identity import DefaultAzureCredential  # noqa: E402
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder  # noqa: E402


def get_client() -> KustoClient:
    cluster_uri = os.environ.get(
        "DETECTIVE_CLUSTER_URI",
        "https://danieldror2.swedencentral.dev.kusto.windows.net/",
    )
    credential = DefaultAzureCredential()
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
        cluster_uri, credential,
    )
    return KustoClient(kcsb)


DATABASE = "MyDatabase"


def _run_command(client: KustoClient, command: str) -> None:
    """Run a management command."""
    client.execute_mgmt(DATABASE, command)


def _run_query(client: KustoClient, query: str) -> int:
    """Run a query and return row count."""
    result = client.execute(DATABASE, query)
    count = 0
    for table in result.primary_results:
        for _ in table:
            count += 1
    return count


def setup_numbers_table(client: KustoClient) -> None:
    """Create Numbers table with the first 200 Fibonacci numbers."""
    print("Setting up Numbers table...")

    # Create table
    _run_command(client, """
        .create-merge table Numbers (N: int, Value: string)
    """)

    # Check if already populated
    count = _run_query(client, "Numbers | count")
    if count >= 200:
        print(f"  Numbers table already has {count} rows, skipping.")
        return

    # Clear and repopulate
    _run_command(client, ".clear table Numbers data")

    # Compute Fibonacci numbers (using Python since KQL can't handle big ints well)
    fibs: list[tuple[int, str]] = []
    a, b = 1, 1
    for i in range(1, 201):
        fibs.append((i, str(a)))
        a, b = b, a + b

    # Ingest in batches via inline ingestion
    batch_size = 20
    for start in range(0, len(fibs), batch_size):
        batch = fibs[start:start + batch_size]
        data_lines = "\n".join(f"{n},{v}" for n, v in batch)
        cmd = f".ingest inline into table Numbers <|\n{data_lines}"
        _run_command(client, cmd)

    count = _run_query(client, "Numbers | count")
    print(f"  Numbers table: {count} rows")

    # Verify the 100th Fibonacci number's second digit
    result = client.execute(DATABASE, """
        Numbers | where N == 100 | project Value
    """)
    for table in result.primary_results:
        for row in table:
            val = str(row["Value"])
            print(f"  F(100) = {val}")
            print(f"  Second digit = {val[1]}")


def setup_cities_table(client: KustoClient) -> None:
    """Create Cities table with timezone data."""
    print("Setting up Cities table...")

    _run_command(client, """
        .create-merge table Cities (Name: string, Continent: string, TimezoneOffsetHours: int)
    """)

    count = _run_query(client, "Cities | count")
    if count >= 10:
        print(f"  Cities table already has {count} rows, skipping.")
        return

    _run_command(client, ".clear table Cities data")

    cities = [
        ("Paris", "Europe", 1),
        ("London", "Europe", 0),
        ("Berlin", "Europe", 1),
        ("Moscow", "Europe", 3),
        ("Istanbul", "Europe", 3),
        ("New York", "North America", -5),
        ("Chicago", "North America", -6),
        ("Denver", "North America", -7),
        ("Los Angeles", "North America", -8),
        ("Tokyo", "Asia", 9),
        ("Beijing", "Asia", 8),
        ("Mumbai", "Asia", 5),
        ("Sydney", "Oceania", 11),
        ("Auckland", "Oceania", 12),
        ("Cairo", "Africa", 2),
        ("Nairobi", "Africa", 3),
    ]

    data_lines = "\n".join(f"{name},{continent},{tz}" for name, continent, tz in cities)
    cmd = f".ingest inline into table Cities <|\n{data_lines}"
    _run_command(client, cmd)

    count = _run_query(client, "Cities | count")
    print(f"  Cities table: {count} rows")

    # Verify: max timezone diff in Europe
    # London=0, Moscow=3, Istanbul=3 → max diff = 3
    result = client.execute(DATABASE, """
        Cities
        | where Continent == "Europe"
        | summarize MinTZ = min(TimezoneOffsetHours), MaxTZ = max(TimezoneOffsetHours)
        | extend Diff = MaxTZ - MinTZ
    """)
    for table in result.primary_results:
        for row in table:
            print(f"  Europe timezone range: {row['MinTZ']} to {row['MaxTZ']}, "
                  f"diff = {row['Diff']}")


def main() -> None:
    client = get_client()

    # Ensure database exists (may need manual creation for free clusters)
    try:
        setup_numbers_table(client)
        setup_cities_table(client)
        print("\n✅ Test data setup complete.")
    except Exception as e:
        print(f"\n❌ Setup failed: {e}", file=sys.stderr)
        print("Make sure you have a 'MyDatabase' database in your cluster.",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
