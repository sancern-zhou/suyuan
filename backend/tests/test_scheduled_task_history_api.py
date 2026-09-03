"""定时任务历史执行记忆 API 测试（隔离存储，不触碰真实数据与真实 LLM）"""
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.scheduled_task_routes import router
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.scheduled_tasks import ScheduledTask, ScheduleType, ScheduledTaskService
from app.scheduled_tasks.storage import (
    ExecutionStorage,
    EventClaimStorage,
    TaskStorage,
)
from app.scheduled_tasks.storage.task_case_storage import TaskCaseStorage

_ADMIN = CurrentUser(
    id="admin-1", username="admin", display_name="管理员", is_admin=True
)
_OTHER = CurrentUser(id="user-2", username="other", display_name="其他用户")


def _make_app(temp_dir):
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
        task_id="task_hist_api",
        name="历史记忆API测试",
        description="测试历史记忆端点",
        schedule_type=ScheduleType.EVERY_30MIN,
        enabled=True,
        prompt="测试提示词",
        timeout_seconds=300,
    )
    service.create_task(task)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: _ADMIN
    return app, service, task


def _storage_factory(temp_dir):
    def _factory(task_id: str) -> TaskCaseStorage:
        return TaskCaseStorage(task_id, base_dir=temp_dir)

    return _factory


def _client(app) -> TestClient:
    return TestClient(app)


def test_history_endpoints_roundtrip():
    temp_dir = tempfile.mkdtemp()
    try:
        app, service, task = _make_app(temp_dir)
        with patch(
            "app.api.scheduled_task_routes.get_scheduled_task_service",
            lambda: service,
        ), patch(
            "app.api.scheduled_task_routes.TaskCaseStorage",
            _storage_factory(temp_dir),
        ):
            client = _client(app)

            # 空历史
            resp = client.get(f"/api/scheduled-tasks/{task.task_id}/history/cases")
            assert resp.status_code == 200
            assert resp.json() == {"cases": [], "total": 0}

            resp = client.get(f"/api/scheduled-tasks/{task.task_id}/history/memory")
            assert resp.status_code == 200
            body = resp.json()
            assert body["memory"] == "" and body["case_count"] == 0

            # 写入案例与记忆
            storage = TaskCaseStorage(task.task_id, base_dir=temp_dir)
            for index in range(3):
                storage.append_case({"execution_id": f"exec_{index}", "status": "succeeded"})
            storage.write_memory("# 任务记忆：历史记忆API测试", {"version": 5})

            # 案例最新在前
            resp = client.get(
                f"/api/scheduled-tasks/{task.task_id}/history/cases",
                params={"limit": 2},
            )
            body = resp.json()
            assert body["total"] == 3
            assert [c["execution_id"] for c in body["cases"]] == ["exec_2", "exec_1"]

            # 记忆读取
            resp = client.get(f"/api/scheduled-tasks/{task.task_id}/history/memory")
            body = resp.json()
            assert "历史记忆API测试" in body["memory"]
            assert body["meta"]["version"] == 5
            assert body["case_count"] == 3

            # 人工编辑记忆：版本递增并标记 manual
            resp = client.put(
                f"/api/scheduled-tasks/{task.task_id}/history/memory",
                json={"content": "# 任务记忆：人工修正\n## 当前关注\n站点A", "expected_version": 5},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["meta"]["version"] == 6
            assert body["meta"]["last_consolidation_status"] == "manual"
            assert "人工修正" in body["memory"]

            # 过期版本不得覆盖最新记忆
            resp = client.put(
                f"/api/scheduled-tasks/{task.task_id}/history/memory",
                json={"content": "# 过期编辑", "expected_version": 5},
            )
            assert resp.status_code == 409

            # 空内容被拒绝
            resp = client.put(
                f"/api/scheduled-tasks/{task.task_id}/history/memory",
                json={"content": "", "expected_version": 6},
            )
            assert resp.status_code == 422
        print("[OK] 历史记忆端点往返测试通过")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_history_access_control():
    temp_dir = tempfile.mkdtemp()
    try:
        app, service, task = _make_app(temp_dir)
        with patch(
            "app.api.scheduled_task_routes.get_scheduled_task_service",
            lambda: service,
        ), patch(
            "app.api.scheduled_task_routes.TaskCaseStorage",
            _storage_factory(temp_dir),
        ):
            app.dependency_overrides[require_current_user] = lambda: _OTHER
            client = _client(app)
            for method, url in [
                ("get", f"/api/scheduled-tasks/{task.task_id}/history/cases"),
                ("get", f"/api/scheduled-tasks/{task.task_id}/history/memory"),
                ("put", f"/api/scheduled-tasks/{task.task_id}/history/memory"),
            ]:
                kwargs = {"json": {"content": "x", "expected_version": 0}} if method == "put" else {}
                resp = getattr(client, method)(url, **kwargs)
                assert resp.status_code == 404, (method, resp.status_code)

            # 任务不存在
            app.dependency_overrides[require_current_user] = lambda: _ADMIN
            resp = client.get("/api/scheduled-tasks/task_missing/history/cases")
            assert resp.status_code == 404
        print("[OK] 历史记忆端点权限测试通过")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_history_endpoints_roundtrip()
    test_history_access_control()
