from __future__ import annotations

import asyncio
import json

import pytest


@pytest.mark.asyncio
async def test_wecom_cli_tool_executes_wecom_cli_without_shell(monkeypatch):
    from app.tools.office.wecom_cli import WeComCliTool

    captured = {}

    class FakeStream:
        def __init__(self, payload: bytes):
            self.payload = payload

        async def read(self) -> bytes:
            return self.payload

    class FakeProcess:
        def __init__(self):
            self.returncode = 0
            self.stdout = FakeStream(b'{"ok": true, "docid": "doc_1"}')
            self.stderr = FakeStream(b"")

        async def wait(self) -> int:
            return self.returncode

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("app.tools.office.wecom_cli.shutil.which", lambda name: "/usr/local/bin/wecom-cli")
    monkeypatch.setattr("app.tools.office.wecom_cli.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    result = await WeComCliTool().execute(
        module="doc",
        command="create",
        payload={"title": "周报", "content": "内容"},
    )

    assert result["success"] is True
    assert result["data"] == {"ok": True, "docid": "doc_1"}
    assert captured["args"] == (
        "/usr/local/bin/wecom-cli",
        "doc",
        "create",
        json.dumps({"title": "周报", "content": "内容"}, ensure_ascii=False),
    )
    assert captured["kwargs"]["stdout"] is asyncio.subprocess.PIPE
    assert captured["kwargs"]["stderr"] is asyncio.subprocess.PIPE


def test_wecom_cli_replaces_direct_wecom_document_tool_in_registry():
    from app.tools import create_global_tool_registry

    registry = create_global_tool_registry()

    assert registry.get_tool("wecom_cli") is not None
    assert registry.get_tool("wecom_document") is None
