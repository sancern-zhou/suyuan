import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _uvicorn_proxy_headers_value(relative_path: str) -> object:
    path = BACKEND_ROOT / relative_path
    assert path.exists(), f"missing supported entrypoint: {relative_path}"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "uvicorn"
            and function.attr == "run"
        ):
            for keyword in node.keywords:
                if keyword.arg == "proxy_headers":
                    return ast.literal_eval(keyword.value)
            return None
    raise AssertionError(f"uvicorn.run not found in {relative_path}")


def test_cli_entrypoints_disable_proxy_header_rewrite():
    for relative_path in (
        "start.sh",
        "restart_server.sh",
        "clean_restart.bat",
        "Dockerfile",
    ):
        path = BACKEND_ROOT / relative_path
        assert path.exists(), f"missing supported entrypoint: {relative_path}"
        source = path.read_text(encoding="utf-8")
        assert "--no-proxy-headers" in source, relative_path


def test_python_entrypoints_disable_proxy_header_rewrite():
    for relative_path in ("app/main.py", "start_windows.py"):
        assert _uvicorn_proxy_headers_value(relative_path) is False, relative_path
