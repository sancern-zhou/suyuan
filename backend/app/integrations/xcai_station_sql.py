"""Minimal XcAi SQL Server connection for background station alerting.

This deliberately does not live below ``app.tools``: fetchers must not load the
global LLM-tool registry merely to read deterministic source data.
"""

from __future__ import annotations

import os


def xcai_connection_string() -> str:
    host = os.getenv("XCAI_SQL_HOST", "180.184.30.94")
    port = os.getenv("XCAI_SQL_PORT", "1433")
    database = os.getenv("XCAI_SQL_DATABASE", "XcAiDb")
    user = os.getenv("XCAI_SQL_USER", "sa")
    password = os.getenv("XCAI_SQL_PASSWORD", "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR")
    return (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={host},{port};DATABASE={database};UID={user};PWD={{{password}}};"
        "TrustServerCertificate=yes;"
    )
