"""Kusto query and exploration tools."""

from detective.kusto_tools import kusto_command, kusto_explore, kusto_query

__tools__ = [kusto_explore, kusto_query, kusto_command]
