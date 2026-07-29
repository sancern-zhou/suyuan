import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
SSE_ROUTES = {
    Path("routers/agent.py"),
    Path("routers/knowledge_qa.py"),
    Path("routers/report_generation.py"),
    Path("routers/expert_deliberation.py"),
}


def _raw_sse_streaming_response_lines(path: Path) -> list[int]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if function_name != "StreamingResponse":
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "media_type"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == "text/event-stream"
            ):
                lines.append(node.lineno)
    return lines


def test_application_has_no_raw_sse_streaming_responses():
    violations = {
        str(path.relative_to(APP_ROOT)): lines
        for path in APP_ROOT.rglob("*.py")
        if "deprecated" not in path.relative_to(APP_ROOT).parts
        if (lines := _raw_sse_streaming_response_lines(path))
    }

    assert violations == {}


def test_every_current_sse_route_uses_the_system_factory():
    for relative_path in SSE_ROUTES:
        source = (APP_ROOT / relative_path).read_text(encoding="utf-8")
        assert "from app.core.sse import create_sse_response" in source
        assert "create_sse_response(" in source
