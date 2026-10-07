# -*- coding: utf-8 -*-
"""Read the source database connection info from sync_config.json (credentials are stored only locally on the server).

Temporary diagnosis/verification scripts uniformly obtain connections through this module,
Credentials must not be hard-coded in code (the code will be tracked by the suyan repository).
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("sync_config.json")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def source_connstr(database: str = "") -> str:
    """Source SQL Server's pyodbc connection string; if database is non-empty, specify the default database."""
    src = load_config()["source"]
    conn_str = (
        f"Driver={{{src['driver']}}};"
        f"Server={src['server']};"
        + (f"Database={database};" if database else "")
        + f"UID={src['user']};PWD={src['password']};"
        "MARS_Connection=yes;"
    )
    return conn_str
