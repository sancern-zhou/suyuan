"""execute_python 错误建议分支：dtype 陷阱与 input_files 未声明指引。"""

from app.tools.utility import execute_python_tool as module


def test_unary_tilde_on_float_suggestion():
    text = module.ExecutePythonTool()._get_error_suggestions(
        "TypeError", "bad operand type for unary ~: 'float'", ""
    )
    assert "fillna(False)" in text
    assert "eq(False)" in text


def test_nan_to_integer_suggestion():
    text = module.ExecutePythonTool()._get_error_suggestions(
        "ValueError", "cannot convert float NaN to integer", ""
    )
    assert "Int64" in text
    assert "pd.notna" in text


def test_missing_session_data_file_suggestion_independent_of_error_type():
    text = module.ExecutePythonTool()._get_error_suggestions(
        "UnknownError", "RuntimeError: 未找到会话数据文件: /tmp/a.json", ""
    )
    assert "input_files" in text


def test_parse_subprocess_error_captures_runtime_error():
    stderr = (
        'Traceback (most recent call last):\n'
        '  File "<string>", line 12, in <module>\n'
        "RuntimeError: 未找到会话数据文件: backend/data/input.json\n"
    )
    info = module.ExecutePythonTool()._parse_subprocess_error(stderr, "x = 1\n" * 11)
    assert info["error_type"] == "RuntimeError"
    assert "input_files" in info["suggestions"]


def test_parse_subprocess_error_unary_tilde():
    stderr = (
        'Traceback (most recent call last):\n'
        '  File "<string>", line 104, in <module>\n'
        "TypeError: bad operand type for unary ~: 'float'\n"
    )
    info = module.ExecutePythonTool()._parse_subprocess_error(stderr, "pass\n" * 103)
    assert info["error_type"] == "TypeError"
    assert "fillna(False)" in info["suggestions"]


def test_load_data_error_message_mentions_input_files(monkeypatch, tmp_path):
    from types import SimpleNamespace

    session_dir = tmp_path / "data"
    session_dir.mkdir()
    source = session_dir / "input.json"
    source.write_text('[{"value": 0}]')
    context = SimpleNamespace(
        data_manager=SimpleNamespace(memory=SimpleNamespace(session=SimpleNamespace(data_dir=session_dir))),
        available_file_paths=[str(source)],
        authorized_input_paths=[],
    )
    code = module.ExecutePythonTool()._inject_data_context(
        "load_data('backend/data/undeclared.json')", context
    )
    try:
        exec(code, {})
    except RuntimeError as exc:
        assert "input_files" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for undeclared file")
