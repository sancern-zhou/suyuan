import importlib
import os
import sys


def test_quick_trace_env_loader_preserves_quoted_hash_password(monkeypatch):
    monkeypatch.delenv("SQLSERVER_PASSWORD", raising=False)
    sys.modules.pop("app.fetchers.quick_trace.quick_trace_fetcher", None)

    importlib.import_module("app.fetchers.quick_trace.quick_trace_fetcher")

    password = os.environ.get("SQLSERVER_PASSWORD")
    assert password
    assert password.startswith("#")
    assert len(password) > 1
