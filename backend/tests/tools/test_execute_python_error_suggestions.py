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


def test_bare_filenotfound_on_session_data_path_teaches_mount_contract():
    """沙箱内 open() 会话数据文件报裸 FileNotFoundError：指引 input_files 契约，不误导为路径写错。"""
    text = module.ExecutePythonTool()._get_error_suggestions(
        "FileNotFoundError",
        "[Errno 2] No such file or directory: "
        "'/workspace/backend/backend_data_registry/sessions/agent_session_x/data/"
        "crawler_sql_query_result--febbd0be.json'",
        "rows=json.load(open(p))",
    )
    assert "input_files" in text
    assert "read_session_resource" in text
    assert "检查文件路径是否正确" not in text


def test_filenotfound_outside_session_data_keeps_generic_advice():
    text = module.ExecutePythonTool()._get_error_suggestions(
        "FileNotFoundError", "[Errno 2] No such file or directory: '/tmp/missing.csv'", ""
    )
    assert "检查文件路径是否正确" in text
    assert "input_files" not in text


def test_repeated_session_file_analysis_gets_wrapup_hint(tmp_path):
    """同一会话数据文件被 execute_python 反复分析时，第3次起结果附收口提醒。"""
    from types import SimpleNamespace

    session_dir = tmp_path / "data"
    session_dir.mkdir()
    data_file = session_dir / "crawler_sql_query_result--abc.json"
    data_file.write_text("[]")
    context = SimpleNamespace(
        data_manager=SimpleNamespace(memory=SimpleNamespace(session=SimpleNamespace(data_dir=session_dir)))
    )
    tool = module.ExecutePythonTool()
    code = f"rows=json.load(open('{data_file}'))\nprint(len(rows))"
    assert tool._session_file_repeat_hint(context, code) == ""
    assert tool._session_file_repeat_hint(context, code) == ""
    hint = tool._session_file_repeat_hint(context, code)
    assert "第3次" in hint and data_file.name in hint and "结论" in hint


def test_repeat_hint_ignores_non_session_paths(tmp_path):
    from types import SimpleNamespace

    session_dir = tmp_path / "data"
    session_dir.mkdir()
    context = SimpleNamespace(
        data_manager=SimpleNamespace(memory=SimpleNamespace(session=SimpleNamespace(data_dir=session_dir)))
    )
    tool = module.ExecutePythonTool()
    code = "rows=json.load(open('/tmp/other.json'))"
    for _ in range(5):
        assert tool._session_file_repeat_hint(context, code) == ""


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
