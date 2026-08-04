import asyncio
import os
import time
from types import SimpleNamespace

import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.tools.utility.execute_python_tool import ExecuteEChartsPythonTool, ExecutePythonTool


def test_python_execution_tools_are_pinned_to_sandbox():
    assert ExecutePythonTool().execution_engine == "bubblewrap"
    assert ExecuteEChartsPythonTool().execution_engine == "bubblewrap"


@pytest.mark.asyncio
async def test_execute_python_does_not_block_worker_event_loop():
    tool = ExecutePythonTool()
    original_cwd = os.getcwd()
    event_loop_progressed = False

    async def mark_progress():
        nonlocal event_loop_progressed
        await asyncio.sleep(0.05)
        event_loop_progressed = True

    progress_task = asyncio.create_task(mark_progress())
    result = await tool.execute(
        code='import time; time.sleep(0.2); print("isolated")',
        timeout=5,
    )
    await progress_task

    assert result["success"] is True
    assert result["data"]["engine"] == "bubblewrap"
    assert "isolated" in result["data"]["output"]
    assert event_loop_progressed is True
    assert os.getcwd() == original_cwd


@pytest.mark.asyncio
async def test_execute_python_publishes_matplotlib_as_one_visual_group():
    result = await ExecutePythonTool().execute(
        code=(
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot([1, 2], [3, 4])\n"
            "save_chart(fig, 'unified-resource-test.png')\n"
        ),
        timeout=10,
    )

    assert result["success"] is True
    resources = [
        ResourceDeclaration.model_validate(item) for item in result["resources"]
    ]
    assert [resource.resource_key for resource in resources] == [
        "chart-spec",
        "chart-image",
    ]
    assert resources[0].renderer.value == "chart"
    assert resources[1].renderer.value == "image"
    assert resources[1].parent_key == resources[0].resource_key
    assert "/api/image/" not in result["summary"]


@pytest.mark.asyncio
async def test_execute_echarts_python_publishes_interactive_catalog_spec_only():
    result = await ExecuteEChartsPythonTool().execute(
        code=(
            "import json\n"
            "option = {'title': {'text': '趋势'}, "
            "'xAxis': {'data': ['A']}, 'yAxis': {}, "
            "'series': [{'type': 'line', 'data': [1]}]}\n"
            "print(json.dumps(option, ensure_ascii=False))\n"
        ),
        timeout=10,
    )

    assert result["success"] is True
    [resource] = [
        ResourceDeclaration.model_validate(item) for item in result["resources"]
    ]
    assert resource.resource_key == "chart-spec"
    assert resource.kind.value == "visual"
    assert resource.renderer.value == "chart"
    assert "image_url" not in result["visuals"][0]
    assert "/api/image/" not in result["summary"]


@pytest.mark.asyncio
async def test_execute_python_timeout_is_a_tool_failure():
    result = await ExecutePythonTool().execute(
        code="import time; time.sleep(5)",
        timeout=1,
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["data"]["error"] == "执行超时"
    assert result["data"]["engine"] == "bubblewrap"


@pytest.mark.asyncio
async def test_large_injected_context_stays_in_subprocess(tmp_path):
    file_path = str(tmp_path / "air_quality.json")
    records = [
        {
            "timestamp": f"2026-07-{(index // 24) + 1:02d} {index % 24:02d}:00:00",
            "measurements": {"AQI": index % 80},
            "padding": "x" * 350,
        }
        for index in range(744)
    ]
    import json

    (tmp_path / "air_quality.json").write_text(
        json.dumps(records, ensure_ascii=False),
        encoding="utf-8",
    )
    context = SimpleNamespace(
        available_file_paths=[file_path],
        data_manager=SimpleNamespace(
            memory=SimpleNamespace(
                session=SimpleNamespace(data_dir=tmp_path),
            ),
        ),
    )

    result = await ExecutePythonTool().execute(
        context=context,
        code=f'records = load_data({file_path!r}); print(len(records))',
        timeout=10,
    )

    assert result["success"] is True
    assert result["data"]["engine"] == "bubblewrap"
    assert result["data"]["output"].strip() == "744"


def test_large_context_is_allowlisted_without_being_embedded(tmp_path):
    file_path = str(tmp_path / "air_quality.json")
    records = [{"value": index, "padding": "x" * 350} for index in range(744)]
    import json

    (tmp_path / "air_quality.json").write_text(json.dumps(records), encoding="utf-8")
    context = SimpleNamespace(available_file_paths=[file_path])
    tool = ExecutePythonTool()

    injected = tool._inject_data_context(
        f"print(len(load_data({file_path!r})))",
        SimpleNamespace(
            available_file_paths=[file_path],
            data_manager=SimpleNamespace(
                memory=SimpleNamespace(session=SimpleNamespace(data_dir=tmp_path)),
            ),
        ),
    )

    assert len(injected) < 10_000
    assert '"padding": "' not in injected


def test_large_echarts_stdout_does_not_block_file_path_detection():
    tool = ExecuteEChartsPythonTool()
    output = '{"series":[{"type":"line","data":[' + ",".join(
        str(index % 100) for index in range(35_000)
    ) + "]}]}"

    started = time.perf_counter()
    paths = tool._extract_file_paths_from_output(output)
    elapsed = time.perf_counter() - started

    assert paths == []
    assert len(output) > 100_000
    assert elapsed < 1.0


def test_file_path_detection_keeps_explicit_markers(tmp_path):
    report_path = tmp_path / "空气质量报告.docx"
    report_path.write_text("test", encoding="utf-8")

    paths = ExecutePythonTool()._extract_file_paths_from_output(
        f"报告已生成：{report_path}\n"
    )

    assert paths == [str(report_path)]


@pytest.mark.asyncio
async def test_bubblewrap_hides_host_files_and_worker_secrets(monkeypatch):
    monkeypatch.setenv("EXECUTE_PYTHON_TEST_SECRET", "must-not-leak")

    result = await ExecutePythonTool().execute(
        code=(
            "import json, os\n"
            "from pathlib import Path\n"
            "print(json.dumps({"
            "'passwd_visible': Path('/etc/passwd').exists(), "
            "'project_visible': Path('/home/xckj/suyuan/backend/app/main.py').exists(), "
            "'secret': os.getenv('EXECUTE_PYTHON_TEST_SECRET')"
            "}))"
        ),
        timeout=5,
    )

    import json

    payload = json.loads(result["data"]["output"])
    assert result["success"] is True
    assert payload == {
        "passwd_visible": False,
        "project_visible": False,
        "secret": None,
    }


def test_bubblewrap_is_fail_closed_when_dependency_is_missing(monkeypatch, tmp_path):
    tool = ExecutePythonTool()
    monkeypatch.setattr(
        "app.tools.utility.execute_python_tool.shutil.which",
        lambda name: None if name == "bwrap" else f"/usr/bin/{name}",
    )

    sandbox_spec = tool._build_bubblewrap_command(
        code="print('test')",
        script_file=str(tmp_path / "script.py"),
        working_dir=str(tmp_path),
        timeout=5,
    )

    assert sandbox_spec is None
