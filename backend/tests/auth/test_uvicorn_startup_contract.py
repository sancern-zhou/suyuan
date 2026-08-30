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
        "Dockerfile",
    ):
        path = BACKEND_ROOT / relative_path
        assert path.exists(), f"missing supported entrypoint: {relative_path}"
        source = path.read_text(encoding="utf-8")
        assert "--no-proxy-headers" in source, relative_path


def test_shell_entrypoints_validate_stable_data_registry_path():
    for relative_path in ("start.sh", "restart_server.sh"):
        source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
        assert "app.utils.deployment_preflight --env-file .env" in source

    worker_source = (BACKEND_ROOT / "app/worker.py").read_text(encoding="utf-8")
    assert "_validate_data_registry_config(sys.argv[1:])" in worker_source


def test_restart_script_recovers_stale_pid_without_cross_project_kill():
    source = (BACKEND_ROOT / "restart_server.sh").read_text(encoding="utf-8")

    assert 'readlink -f "/proc/${candidate_pid}/cwd"' in source
    assert '[[ "${candidate_cwd}" = "${SCRIPT_DIR}" ]]' in source
    assert '[[ "${OLD_PID}" =~ ^[0-9]+$ ]]' in source
    assert "# PID文件可能缺失、过期或只记录了其中一个实例" in source
    assert 'mapfile -t RUNNING_PIDS' in source
    assert 'is_backend_listener_ready "${NEW_PID}"' in source


def test_python_entrypoints_disable_proxy_header_rewrite():
    for relative_path in ("app/main.py",):
        assert _uvicorn_proxy_headers_value(relative_path) is False, relative_path
