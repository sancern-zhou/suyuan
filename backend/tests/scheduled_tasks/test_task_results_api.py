"""定时任务结构化执行结果 API 测试（列表筛选、facets、文件与报告内容端点）"""
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.scheduled_task_routes import router
from app.auth.dependencies import optional_current_user, require_current_user
from app.auth.models import CurrentUser
from app.scheduled_tasks import ScheduledTask, ScheduleType, ScheduledTaskService
from app.scheduled_tasks.models.result import TaskResult
from app.scheduled_tasks.storage import (
    ExecutionStorage,
    EventClaimStorage,
    TaskStorage,
)

_ADMIN = CurrentUser(
    id="admin-1", username="admin", display_name="管理员", is_admin=True
)


def _result(**overrides) -> TaskResult:
    payload = dict(
        execution_id="exec-1",
        task_id="task_results_api",
        task_name="结果API测试",
        session_id="session-1",
        status="success",
        started_at=datetime(2026, 9, 1, 8, 0, 0),
        completed_at=datetime(2026, 9, 1, 8, 5, 0),
        city="许昌市",
        station_id="station-1",
        station_name="监测一站",
        pollutant="PM2.5",
        conclusion="结论正文",
        findings=["发现一"],
        image_paths=[],
        document_paths=[],
        evidence_package_paths=[],
        report_refs=[],
    )
    payload.update(overrides)
    return TaskResult(**payload)


def _make_app(temp_dir: Path):
    def mock_agent_factory():
        class MockAgent:
            async def analyze(self, prompt, **kwargs):
                yield {"type": "final_response", "content": "完成"}

        return MockAgent()

    service = ScheduledTaskService(
        agent_factory=mock_agent_factory,
        task_storage=TaskStorage(storage_dir=temp_dir),
        execution_storage=ExecutionStorage(storage_dir=temp_dir),
        claim_storage=EventClaimStorage(storage_dir=temp_dir),
    )
    task = ScheduledTask(
        task_id="task_results_api",
        name="结果API测试",
        description="测试结果端点",
        schedule_type=ScheduleType.EVERY_30MIN,
        enabled=True,
        prompt="测试提示词",
        timeout_seconds=300,
    )
    service.create_task(task)

    records = [
        _result(
            execution_id="exec-1",
            station_id="station-1",
            station_name="监测一站",
            pollutant="PM2.5",
        ),
        _result(
            execution_id="exec-2",
            completed_at=datetime(2026, 9, 2, 8, 5, 0),
            station_id="station-2",
            station_name="监测二站",
            pollutant="PM10",
        ),
    ]

    def fake_list_task_results(**kwargs):
        filtered = records
        if kwargs.get("task_id"):
            filtered = [r for r in filtered if r.task_id == kwargs["task_id"]]
        if kwargs.get("station_id"):
            filtered = [r for r in filtered if r.station_id == kwargs["station_id"]]
        if kwargs.get("pollutant"):
            filtered = [r for r in filtered if r.pollutant == kwargs["pollutant"]]
        if kwargs.get("started_after"):
            filtered = [
                r for r in filtered
                if r.completed_at and r.completed_at >= kwargs["started_after"]
            ]
        if kwargs.get("started_before"):
            filtered = [
                r for r in filtered
                if r.completed_at and r.completed_at <= kwargs["started_before"]
            ]
        return filtered, len(filtered)

    def fake_facets(**kwargs):
        return {
            "stations": [
                {"station_id": "station-1", "station_name": "监测一站"},
                {"station_id": "station-2", "station_name": "监测二站"},
            ],
            "pollutants": ["PM10", "PM2.5"],
        }

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: _ADMIN
    app.dependency_overrides[optional_current_user] = lambda: _ADMIN
    patches = [
        patch(
            "app.api.scheduled_task_routes.get_scheduled_task_service",
            lambda: service,
        ),
        patch.object(service, "list_task_results", staticmethod(fake_list_task_results)),
        patch.object(service, "get_task_result", staticmethod(lambda eid: next(
            (r for r in records if r.execution_id == eid), None
        ))),
        patch.object(service, "list_task_result_facets", staticmethod(fake_facets)),
    ]
    for item in patches:
        item.start()
    yield app, service, task, records, temp_dir
    for item in patches:
        item.stop()


def _client(app) -> TestClient:
    return TestClient(app)


def test_results_list_supports_filters_and_tickets():
    temp_dir = Path(tempfile.mkdtemp())
    try:
        for app, _service, task, _records, _dir in _make_app(temp_dir):
            client = _client(app)

            resp = client.get(f"/api/scheduled-tasks/results?task_id={task.task_id}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 2
            assert len(body["results"]) == 2
            first = body["results"][0]
            assert first["preview_ticket"]
            assert first["has_report"] is False
            assert first["station_name"] == "监测一站"

            resp = client.get(
                f"/api/scheduled-tasks/results?task_id={task.task_id}"
                "&station_id=station-2&pollutant=PM10"
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            assert body["results"][0]["execution_id"] == "exec-2"

            resp = client.get(
                f"/api/scheduled-tasks/results?task_id={task.task_id}"
                "&start=2026-09-02T00:00:00"
            )
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_results_facets_endpoint():
    temp_dir = Path(tempfile.mkdtemp())
    try:
        for app, _service, task, _records, _dir in _make_app(temp_dir):
            client = _client(app)
            resp = client.get(f"/api/scheduled-tasks/results/facets?task_id={task.task_id}")
            assert resp.status_code == 200
            body = resp.json()
            assert [s["station_id"] for s in body["stations"]] == ["station-1", "station-2"]
            assert body["pollutants"] == ["PM10", "PM2.5"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_result_file_endpoint_serves_recorded_path():
    temp_dir = Path(tempfile.mkdtemp())
    try:
        image = temp_dir / "chart.png"
        image.write_bytes(b"png-bytes")

        for app, _service, task, records, _dir in _make_app(temp_dir):
            records[0].image_paths = [str(image)]
            client = _client(app)
            resp = client.get(
                f"/api/scheduled-tasks/results/exec-1/files/images/0"
            )
            assert resp.status_code == 200
            assert resp.content == b"png-bytes"
            assert resp.headers["content-type"].startswith("image/png")

            resp = client.get(
                f"/api/scheduled-tasks/results/exec-1/files/images/9"
            )
            assert resp.status_code == 404
            records[0].image_paths = []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_result_report_endpoint_serves_html_and_assets():
    temp_dir = Path(tempfile.mkdtemp())
    try:
        reports_root = temp_dir / "reports"
        report_dir = reports_root / "report-abc"
        report_dir.mkdir(parents=True)
        (report_dir / "report.html").write_text(
            "<html><body><img src='chart.png'></body></html>", encoding="utf-8"
        )
        (report_dir / "chart.png").write_bytes(b"png-bytes")

        for app, _service, task, records, _dir in _make_app(temp_dir):
            records[0].report_refs = [{"kind": "report", "ref": "report-abc"}]
            from app.services.quarto_report_renderer import quarto_report_renderer

            with patch.object(
                quarto_report_renderer,
                "get_report_dir",
                lambda report_id: reports_root / report_id,
            ), patch.object(
                quarto_report_renderer, "report_root", reports_root
            ):
                client = _client(app)

                resp = client.get("/api/scheduled-tasks/results/exec-1/report")
                assert resp.status_code == 200
                assert b"<html>" in resp.content
                assert resp.headers["content-type"].startswith("text/html")

                resp = client.get("/api/scheduled-tasks/results/exec-1/report/chart.png")
                assert resp.status_code == 200
                assert resp.content == b"png-bytes"

                resp = client.get(
                    "/api/scheduled-tasks/results/exec-1/report/../../secret.txt"
                )
                assert resp.status_code in (403, 404)

                records[0].report_refs = []
                resp = client.get("/api/scheduled-tasks/results/exec-1/report")
                assert resp.status_code == 404
                records[0].report_refs = [{"kind": "report", "ref": "report-abc"}]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_report_formats_lists_available_exports_with_download_urls():
    temp_dir = Path(tempfile.mkdtemp())
    try:
        reports_root = temp_dir / "reports"
        report_dir = reports_root / "report-abc"
        report_dir.mkdir(parents=True)
        (report_dir / "report.html").write_text("<html>ok</html>", encoding="utf-8")
        (report_dir / "report.docx").write_bytes(b"docx-bytes")

        for app, service, task, records, _dir in _make_app(temp_dir):
            records[0].report_refs = [{"kind": "report", "ref": "report-abc"}]
            from app.services.quarto_report_renderer import quarto_report_renderer

            with patch.object(
                quarto_report_renderer,
                "get_report_dir",
                lambda report_id: reports_root / report_id,
            ), patch.object(
                quarto_report_renderer, "report_root", reports_root
            ):
                client = _client(app)
                resp = client.get(
                    f"/api/scheduled-tasks/results/exec-1/report/formats"
                )
                assert resp.status_code == 200
                body = resp.json()
                by_format = {item["format"]: item for item in body["formats"]}
                assert set(by_format) == {"docx", "html"}
                assert "attachment" in by_format["docx"]["url"]

                # 下载请求使用 attachment 处置
                resp = client.get(by_format["docx"]["url"])
                assert resp.status_code == 200
                assert resp.headers["content-disposition"].startswith("attachment")

                # 不存在的格式不会列出；QMD 源文件未生成时不出现
                records[0].report_refs = []
                resp = client.get(f"/api/scheduled-tasks/results/exec-1/report/formats")
                assert resp.status_code == 200
                assert resp.json() == {"formats": []}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_result_content_requires_ticket_for_anonymous_requests():
    temp_dir = Path(tempfile.mkdtemp())
    try:
        image = temp_dir / "chart.png"
        image.write_bytes(b"png-bytes")
        for app, service, _task, records, _dir in _make_app(temp_dir):
            records[0].image_paths = [str(image)]
            anonymous_app = FastAPI()
            anonymous_app.include_router(router)
            anonymous_app.dependency_overrides.pop(optional_current_user, None)
            patches = [
                patch(
                    "app.api.scheduled_task_routes.get_scheduled_task_service",
                    lambda: service,
                ),
                patch.object(service, "get_task_result", staticmethod(lambda eid: next(
                    (r for r in records if r.execution_id == eid), None
                ))),
            ]
            for item in patches:
                item.start()
            try:
                client = TestClient(anonymous_app)
                resp = client.get("/api/scheduled-tasks/results/exec-1/files/images/0")
                assert resp.status_code == 401

                from app.auth.share_access import get_share_access_service

                ticket = get_share_access_service().issue(
                    "scheduled-task-result", "exec-1"
                )
                resp = client.get(
                    f"/api/scheduled-tasks/results/exec-1/files/images/0"
                    f"?preview_ticket={ticket}"
                )
                assert resp.status_code == 200
                assert resp.content == b"png-bytes"
            finally:
                for item in patches:
                    item.stop()
            records[0].image_paths = []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_report_accepts_path_segment_ticket_without_user():
    """回归：iframe 报告 URL 的票据在路径段中（_t/{ticket}/），必须被端点接受。"""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        reports_root = temp_dir / "reports"
        report_dir = reports_root / "report-abc"
        report_dir.mkdir(parents=True)
        (report_dir / "report.html").write_text("<html>ok</html>", encoding="utf-8")
        (report_dir / "chart.png").write_bytes(b"png-bytes")

        for app, service, _task, records, _dir in _make_app(temp_dir):
            records[0].report_refs = [{"kind": "report", "ref": "report-abc"}]
            from app.auth.share_access import get_share_access_service
            from app.services.quarto_report_renderer import quarto_report_renderer

            anonymous_app = FastAPI()
            anonymous_app.include_router(router)
            with patch.object(
                quarto_report_renderer,
                "get_report_dir",
                lambda report_id: reports_root / report_id,
            ), patch.object(
                quarto_report_renderer, "report_root", reports_root
            ), patch(
                "app.api.scheduled_task_routes.get_scheduled_task_service",
                lambda: service,
            ), patch.object(service, "get_task_result", staticmethod(lambda eid: next(
                (r for r in records if r.execution_id == eid), None
            ))):
                client = TestClient(anonymous_app)
                ticket = get_share_access_service().issue(
                    "scheduled-task-result", "exec-1"
                )

                # 无 Bearer、无查询参数、无 cookie——票据仅在路径段中
                resp = client.get(
                    f"/api/scheduled-tasks/results/exec-1/report/_t/{ticket}/report.html"
                )
                assert resp.status_code == 200
                assert resp.content == b"<html>ok</html>"
                # 回归：attachment 会让 iframe 触发下载而非渲染，必须为 inline
                assert resp.headers["content-disposition"].startswith("inline")

                # 相对资源继承同一路径票据
                resp = client.get(
                    f"/api/scheduled-tasks/results/exec-1/report/_t/{ticket}/chart.png"
                )
                assert resp.status_code == 200
                assert resp.content == b"png-bytes"

                # 错误票据仍拒绝
                resp = client.get(
                    "/api/scheduled-tasks/results/exec-1/report/_t/bogus/report.html"
                )
                assert resp.status_code == 401
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
