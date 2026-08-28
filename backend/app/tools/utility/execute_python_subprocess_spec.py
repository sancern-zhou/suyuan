import asyncio
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from matplotlib import font_manager

from app.agent.resources.contracts import ResourceDeclaration
from app.tools.utility.execute_python_tool import ExecuteEChartsPythonTool, ExecutePythonTool
from app.utils.font_utils import select_preferred_chinese_font_path


def test_python_execution_tools_are_pinned_to_sandbox():
    assert ExecutePythonTool().execution_engine == "bubblewrap"
    assert ExecuteEChartsPythonTool().execution_engine == "bubblewrap"


@pytest.mark.asyncio
async def test_execute_python_defaults_matplotlib_to_preferred_biaosong():
    font_path = select_preferred_chinese_font_path()
    assert font_path is not None
    expected_name = font_manager.FontProperties(fname=str(font_path)).get_name()

    result = await ExecutePythonTool().execute(
        code=(
            "import matplotlib.pyplot as plt\n"
            "print('SUYUAN_FONT=' + plt.rcParams['font.sans-serif'][0])\n"
        ),
        timeout=10,
    )

    assert result["success"] is True
    assert f"SUYUAN_FONT={expected_name}" in result["data"]["output"]


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
    assert "Do not place this server path" in result["llm_resume"]["tool_hint"]


@pytest.mark.asyncio
async def test_execute_python_publishes_qmd_as_rendered_report_package(monkeypatch, tmp_path):
    from app.tools import artifact_utils

    report_dir = tmp_path / "reports" / "source_qmd_demo"
    package_qmd = report_dir / "report.qmd"
    package_html = report_dir / "report.html"
    package_qmd.parent.mkdir(parents=True)
    package_qmd.write_text("# Report", encoding="utf-8")
    package_html.write_text("<h1>Report</h1>", encoding="utf-8")

    def fake_attach(data, path, *, generator):
        assert str(path).lower().endswith(".qmd")
        artifact_utils.attach_report_package_resources(
            data,
            package_qmd,
            report_id="source_qmd_demo",
            html_path=package_html,
            generator=generator,
        )
        data["resources"][0]["label"] = Path(path).name
        return True

    monkeypatch.setattr(
        "app.tools.utility.execute_python_tool.attach_rendered_qmd_report_resources",
        fake_attach,
    )

    result = await ExecutePythonTool().execute(
        code=(
            "from pathlib import Path\n"
            "Path('draft_report.qmd').write_text('# Report', encoding='utf-8')\n"
        ),
        timeout=10,
    )

    assert result["success"] is True
    resources = [
        ResourceDeclaration.model_validate(item) for item in result["resources"]
    ]
    assert [resource.resource_key for resource in resources] == ["qmd", "html"]
    assert resources[0].group_key == "report:source_qmd_demo"
    assert resources[0].relation.value == "primary"
    assert resources[0].label.startswith("draft_report")
    assert resources[0].label.endswith(".qmd")
    assert "render" in {item.value for item in resources[0].capabilities}
    assert resources[1].relation.value == "preview"
    assert resources[1].renderer.value == "html"
    assert resources[1].parent_key == "qmd"


@pytest.mark.asyncio
async def test_execute_python_keeps_qmd_downloadable_when_render_fails(monkeypatch):
    def fake_attach(data, _path, *, generator):
        del generator
        data["preview_error"] = "quarto unavailable"
        return False

    monkeypatch.setattr(
        "app.tools.utility.execute_python_tool.attach_rendered_qmd_report_resources",
        fake_attach,
    )

    result = await ExecutePythonTool().execute(
        code=(
            "from pathlib import Path\n"
            "Path('draft_report.qmd').write_text('# Report', encoding='utf-8')\n"
        ),
        timeout=10,
    )

    assert result["success"] is True
    [resource] = [
        ResourceDeclaration.model_validate(item) for item in result["resources"]
    ]
    assert resource.resource_key == "primary:qmd"
    assert resource.relation.value == "primary"
    assert resource.renderer.value == "markdown"
    assert {item.value for item in resource.capabilities} == {"preview", "download"}
    assert result["data"]["preview_error"] == "quarto unavailable"


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
