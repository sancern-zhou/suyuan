"""
任务级历史案例存储

每个定时任务拥有独立目录（互不共享）：
    backend_data_registry/scheduled_tasks/memory/{task_id}/
    - cases.jsonl       案例库（追加式，每行一个案例 JSON，仅保留最近 MAX_CASES 条）
    - MEMORY.md         任务专属长期记忆（由执行后巩固调用维护）
    - memory_meta.json  巩固元信息（版本/状态/失败计数）

案例只记录单次执行的回顾性事实；面向未来的经验沉淀在 MEMORY.md 中。
"""
import json
import shutil
from pathlib import Path
from typing import Any

from app.utils.path_config import get_data_registry


class TaskCaseStorage:
    """单个定时任务的历史案例与长期记忆存储"""

    MAX_CASES = 1000  # 案例库上限（超出时裁掉最旧的，长期结论已沉淀进 MEMORY.md）

    def __init__(self, task_id: str, base_dir: str | Path | None = None):
        base = Path(base_dir) if base_dir else get_data_registry() / "scheduled_tasks" / "memory"
        self.task_id = task_id
        self.task_dir = base / task_id
        self.cases_file = self.task_dir / "cases.jsonl"
        self.memory_file = self.task_dir / "MEMORY.md"
        self.meta_file = self.task_dir / "memory_meta.json"

    def append_case(self, case: dict[str, Any]) -> None:
        """追加一条案例（JSONL），并按需裁剪案例库。"""
        self.task_dir.mkdir(parents=True, exist_ok=True)
        with open(self.cases_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(case, ensure_ascii=False, default=str) + "\n")
        self._prune_cases()

    def _prune_cases(self) -> None:
        try:
            lines = self.cases_file.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return
        non_empty = [line for line in lines if line.strip()]
        if len(non_empty) <= self.MAX_CASES:
            return
        kept = non_empty[-self.MAX_CASES:]
        tmp = self.cases_file.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        tmp.replace(self.cases_file)

    def recent_cases(self, limit: int) -> list[dict[str, Any]]:
        """读取最近 limit 条案例，按时间正序（旧→新）返回。"""
        if limit <= 0:
            return []
        try:
            lines = self.cases_file.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        cases: list[dict[str, Any]] = []
        for line in reversed(lines):
            if len(cases) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        cases.reverse()
        return cases

    def case_count(self) -> int:
        try:
            lines = self.cases_file.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return 0
        return sum(1 for line in lines if line.strip())

    def read_memory(self) -> str:
        try:
            return self.memory_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def write_memory(self, content: str, meta: dict[str, Any]) -> None:
        """覆盖写入长期记忆与巩固元信息（原子替换）。"""
        self.task_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.memory_file.with_suffix(".md.tmp")
        tmp.write_text(content.rstrip() + "\n", encoding="utf-8")
        tmp.replace(self.memory_file)
        self.write_meta(meta)

    def write_meta(self, meta: dict[str, Any]) -> None:
        self.task_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.meta_file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(self.meta_file)

    def read_meta(self) -> dict[str, Any]:
        try:
            return json.loads(self.meta_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def delete(self) -> bool:
        """删除该任务的全部历史（案例库 + 长期记忆）。"""
        if self.task_dir.exists():
            shutil.rmtree(self.task_dir)
            return True
        return False
