import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.utility import execute_python_tool as module
from app.utils.path_config import resolve_agent_path


def session_context(directory, **kwargs):
    return SimpleNamespace(
        data_manager=SimpleNamespace(memory=SimpleNamespace(session=SimpleNamespace(data_dir=directory))),
        available_file_paths=[], authorized_input_paths=[], **kwargs,
    )


@pytest.mark.asyncio
async def test_save_reload_with_read_only_parent_mount(monkeypatch, tmp_path):
    from app.agent.context import data_files
    registry = tmp_path / "registry"
    (registry / "images").mkdir(parents=True)
    session_dir = registry / "sessions" / "test" / "data"
    session_dir.mkdir(parents=True)
    original = session_dir / "input.json"
    original.write_text('[{"value": 1}]')
    sibling = registry / "protected.json"
    sibling.write_text('["protected"]')
    monkeypatch.setattr(module, "get_data_registry", lambda: registry)
    monkeypatch.setattr(data_files, "get_data_registry", lambda: registry)
    monkeypatch.setattr(module, "get_images_dir", lambda: registry / "images")
    context = session_context(session_dir)
    context.authorized_input_paths = [str(registry)]
    context.available_file_paths = [str(original)]
    tool = module.ExecutePythonTool()
    tool.max_output_size = 32
    result = await tool.execute(context=context, code=(
        f"rows = load_data({str(original)!r})\n"
        "rows[0]['value'] = 2\n"
        "saved = save_data(rows, schema='weather')\n"
        "assert load_data(saved) == rows\n"
        "try:\n"
        f"    open({str(sibling)!r}, 'w').write('changed')\n"
        "except OSError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('Registry parent became writable')\n"
    ))
    assert result["success"] is True, result
    [saved_path] = result["data"]["data_file_paths"]
    assert json.loads(resolve_agent_path(saved_path).read_text()) == [{"value": 2}]
    assert json.loads(original.read_text()) == [{"value": 1}]
    assert json.loads(sibling.read_text()) == ["protected"]
    assert result["resources"]
    reloaded = await tool.execute(context=context, code=f"assert load_data({saved_path!r}) == [{{'value': 2}}]\nprint('RELOADED')")
    assert reloaded["success"] is True, reloaded
    assert "RELOADED" in reloaded["data"]["output"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "invalid", "outside"])
async def test_save_marker_requires_readable_session_json(tmp_path, failure):
    session_dir = tmp_path / "data"
    session_dir.mkdir()
    path = session_dir / "missing.json"
    if failure == "invalid":
        path.write_text("not json")
    elif failure == "outside":
        path = tmp_path / "outside.json"
        path.write_text("[]")
    tool = module.ExecutePythonTool()
    result = await tool.execute(context=session_context(session_dir), code=f"print('PYTHON_DATA_FILE_SAVED:{path}')")
    assert result["success"] is False
    assert result["error_code"] == "DATA_FILE_NOT_AVAILABLE"
    assert not result["data"].get("data_file_paths")
    assert not result.get("resources")


@pytest.mark.asyncio
async def test_python_error_has_machine_readable_failure():
    result = await module.ExecutePythonTool().execute(code="raise ValueError('contract failure')")
    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["error_code"] == "PYTHON_EXECUTION_FAILED"
    assert "contract failure" in result["error"]
    assert result["next_action"]


def test_load_data_resolves_project_paths_without_using_cwd(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "resolve_agent_path", lambda value: (tmp_path / Path(value)).resolve())
    session_dir = tmp_path / "backend" / "registry" / "data"
    session_dir.mkdir(parents=True)
    source = session_dir / "input.json"
    source.write_text('[{"value": 0}]')
    context = session_context(session_dir)
    context.available_file_paths = [str(source)]
    code = module.ExecutePythonTool()._inject_data_context("assert load_data('backend/registry/data/input.json') == [{'value': 0}]", context)
    exec(code, {})


@pytest.mark.asyncio
async def test_save_data_prints_truncated_shape_and_keeps_full_sidecar(monkeypatch, tmp_path):
    import re

    from app.agent.context import data_files

    registry = tmp_path / "registry"
    session_dir = registry / "sessions" / "test" / "data"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(module, "get_data_registry", lambda: registry)
    monkeypatch.setattr(data_files, "get_data_registry", lambda: registry)

    def fake_get_data_shape(path):
        sidecar = resolve_agent_path(path).with_suffix(".data_shape.json")
        if sidecar.is_file():
            return json.loads(sidecar.read_text())
        return None

    context = session_context(session_dir, get_data_shape=fake_get_data_shape)
    tool = module.ExecutePythonTool()
    code = (
        "row = {f'col_{i}': i for i in range(40)}\n"
        "saved = save_data([row], schema='wide')\n"
        "print('SAVED', saved)\n"
    )
    result = await tool.execute(context=context, code=code)
    assert result["success"] is True, result

    [saved_path] = result["data"]["data_file_paths"]
    output = result["data"]["output"]

    # stdout 只带截断形状：前 12 列 + columns_total，宽表不得灌爆 LLM 上下文
    shape_line = re.search(r"PYTHON_DATA_FILE_SHAPE:\S+:(\{.*\})", output)
    assert shape_line, output
    printed = json.loads(shape_line.group(1))
    assert len(printed["columns"]) == module.MAX_SHAPE_COLUMNS
    assert printed["columns_total"] == 40
    assert "col_39" not in output
    assert len(output) < 2000

    # sidecar 保存全量形状
    sidecar = resolve_agent_path(saved_path).with_suffix(".data_shape.json")
    full_shape = json.loads(sidecar.read_text())
    assert len(full_shape["columns"]) == 40
    assert "columns_total" not in full_shape

    # 结果里的 data_shapes 优先采用 sidecar 全量形状
    registered = result["data_shapes"][saved_path]
    assert len(registered["columns"]) == 40
    assert "columns_total" not in registered
