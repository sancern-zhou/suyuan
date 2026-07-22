import asyncio
import json

import pytest

from app.tools.office.editable_ppt.compiler_client import CompilerClientError, EditablePptCompilerClient


class FakeProcess:
    def __init__(self, stdout=b'{"success":true,"dirtySlides":["cover"]}\n', stderr=b"", code=0, delay=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = code
        self.delay = delay
        self.killed = False
        self.payload = None

    async def communicate(self, payload):
        self.payload = payload
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.stdout, self.stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        self.returncode = -9


@pytest.mark.asyncio
async def test_compile_sends_one_json_request_and_parses_response(tmp_path, monkeypatch):
    process = FakeProcess()
    async def factory(*args, **kwargs):
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    result = await EditablePptCompilerClient().compile(tmp_path, dirty_slides=["cover"])
    assert result["success"] is True
    assert json.loads(process.payload)["dirtySlides"] == ["cover"]
    assert json.loads(process.payload)["editable"] == "strict"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("process", "code"),
    [
        (FakeProcess(stdout=b"not-json\n"), "COMPILER_PROTOCOL_ERROR"),
        (FakeProcess(stdout=b"{}\n{}\n"), "COMPILER_PROTOCOL_ERROR"),
        (FakeProcess(stdout=b"", stderr=b"boom", code=2), "COMPILER_PROCESS_FAILED"),
    ],
)
async def test_protocol_and_process_errors(process, code, tmp_path, monkeypatch):
    async def factory(*args, **kwargs):
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    with pytest.raises(CompilerClientError) as error:
        await EditablePptCompilerClient().inspect(tmp_path)
    assert error.value.code == code


@pytest.mark.asyncio
async def test_timeout_kills_compiler(tmp_path, monkeypatch):
    process = FakeProcess(delay=0.1)
    async def factory(*args, **kwargs):
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    client = EditablePptCompilerClient(timeout_seconds=0.01)
    with pytest.raises(CompilerClientError) as error:
        await client.inspect(tmp_path)
    assert error.value.code == "COMPILER_TIMEOUT"
    assert process.killed is True


@pytest.mark.asyncio
async def test_missing_node_has_stable_error(tmp_path, monkeypatch):
    async def factory(*args, **kwargs):
        raise FileNotFoundError("node")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    with pytest.raises(CompilerClientError) as error:
        await EditablePptCompilerClient(node_binary="missing-node").inspect(tmp_path)
    assert error.value.code == "NODE_RUNTIME_MISSING"
