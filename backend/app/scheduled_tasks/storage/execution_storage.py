"""
执行记录存储层 - JSON文件存储
保留最近50条执行记录
"""
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta

from ..models.execution import TaskExecution, ExecutionStatus


class ExecutionStorage:
    """执行记录存储"""

    MAX_RECORDS = 50  # 最多保留50条记录

    def __init__(self, storage_dir: str = "backend_data_registry/scheduled_tasks"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.executions_file = self.storage_dir / "executions.json"

        # 初始化文件
        if not self.executions_file.exists():
            self._write_executions([])

    def _read_executions(self) -> List[dict]:
        """读取所有执行记录"""
        try:
            with open(self.executions_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write_executions(self, executions: List[dict]):
        """写入执行记录"""
        with open(self.executions_file, "w", encoding="utf-8") as f:
            json.dump(executions, f, ensure_ascii=False, indent=2, default=str)

    def _cleanup_old_records(self, executions: List[dict]) -> List[dict]:
        """清理旧记录，保留最近50条"""
        if len(executions) <= self.MAX_RECORDS:
            return executions

        # 按开始时间排序，保留最新的50条
        executions.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return executions[:self.MAX_RECORDS]

    def create(self, execution: TaskExecution) -> TaskExecution:
        """创建执行记录"""
        executions = self._read_executions()

        # 添加记录
        exec_dict = execution.model_dump(mode="json")
        executions.append(exec_dict)

        # 清理旧记录
        executions = self._cleanup_old_records(executions)

        self._write_executions(executions)
        return execution

    def get(self, execution_id: str) -> Optional[TaskExecution]:
        """获取执行记录"""
        executions = self._read_executions()
        for exec_dict in executions:
            if exec_dict["execution_id"] == execution_id:
                return TaskExecution(**exec_dict)
        return None

    def update(self, execution: TaskExecution) -> TaskExecution:
        """更新执行记录"""
        executions = self._read_executions()
        updated = False

        for i, exec_dict in enumerate(executions):
            if exec_dict["execution_id"] == execution.execution_id:
                executions[i] = execution.model_dump(mode="json")
                updated = True
                break

        if not updated:
            raise ValueError(f"Execution {execution.execution_id} not found")

        self._write_executions(executions)
        return execution

    def list_by_task(
        self,
        task_id: str,
        limit: int = 10,
        status: Optional[ExecutionStatus] = None
    ) -> List[TaskExecution]:
        """列出任务的执行记录"""
        executions = self._read_executions()
        result = []

        for exec_dict in executions:
            if exec_dict["task_id"] != task_id:
                continue

            if status and exec_dict.get("status") != status.value:
                continue

            result.append(TaskExecution(**exec_dict))

        # 按开始时间倒序排序
        result.sort(key=lambda x: x.started_at, reverse=True)

        return result[:limit]

    def list_recent(
        self,
        limit: int = 20,
        status: Optional[ExecutionStatus] = None
    ) -> List[TaskExecution]:
        """列出最近的执行记录"""
        executions = self._read_executions()
        result = []

        for exec_dict in executions:
            if status and exec_dict.get("status") != status.value:
                continue

            result.append(TaskExecution(**exec_dict))

        # 按开始时间倒序排序
        result.sort(key=lambda x: x.started_at, reverse=True)

        return result[:limit]

    def get_running_executions(self) -> List[TaskExecution]:
        """获取所有运行中的执行"""
        executions = self._read_executions()
        result = []

        for exec_dict in executions:
            if exec_dict.get("status") == ExecutionStatus.RUNNING.value:
                result.append(TaskExecution(**exec_dict))

        return result

    def delete_by_task(self, task_id: str) -> int:
        """删除任务的所有执行记录"""
        executions = self._read_executions()
        original_len = len(executions)

        executions = [e for e in executions if e["task_id"] != task_id]
        deleted_count = original_len - len(executions)

        if deleted_count > 0:
            self._write_executions(executions)

        return deleted_count

    def get_statistics(self, task_id: Optional[str] = None, days: int = 7) -> dict:
        """获取统计信息"""
        executions = self._read_executions()
        cutoff_time = datetime.now() - timedelta(days=days)

        # 过滤条件
        filtered = []
        for exec_dict in executions:
            if task_id and exec_dict["task_id"] != task_id:
                continue

            started_at = datetime.fromisoformat(exec_dict["started_at"])
            if started_at < cutoff_time:
                continue

            filtered.append(exec_dict)

        # 统计
        total = len(filtered)
        success = sum(1 for e in filtered if e.get("status") == ExecutionStatus.SUCCESS.value)
        failed = sum(1 for e in filtered if e.get("status") == ExecutionStatus.FAILED.value)
        running = sum(1 for e in filtered if e.get("status") == ExecutionStatus.RUNNING.value)

        # 平均执行时长
        durations = [e.get("duration_seconds", 0) for e in filtered if e.get("duration_seconds")]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "running": running,
            "success_rate": success / total if total > 0 else 0,
            "avg_duration_seconds": avg_duration,
            "period_days": days
        }
