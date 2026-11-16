"""Guangdong project scheduled-task manifest consistency guard.

The startup bootstrap (`sync_project_scheduled_tasks`) only registers tasks
listed in ``projects/guangdong/project.yaml`` → ``scheduled_tasks``; a seed
JSON that is not listed silently never runs.  This test keeps the manifest and
the seed directory in two-way sync.
"""

from __future__ import annotations

from pathlib import Path

from app.project_config.loader import load_project_context
from app.scheduled_tasks.models import ScheduledTask

PROJECT_ID = "guangdong"


def _project_root() -> Path:
    from app.utils.path_config import PROJECT_ROOT

    return PROJECT_ROOT


def _seed_dir() -> Path:
    return _project_root() / "projects" / PROJECT_ID / "scheduled_tasks"


def test_manifest_lists_every_seed_and_vice_versa() -> None:
    context = load_project_context(PROJECT_ID)
    manifest_ids = set(context.manifest.scheduled_tasks)
    seed_ids = {path.stem for path in _seed_dir().glob("*.json")}

    missing_in_manifest = sorted(seed_ids - manifest_ids)
    missing_seed_files = sorted(manifest_ids - seed_ids)
    assert not missing_in_manifest, (
        f"种子任务未登记进 project.yaml scheduled_tasks（启动引导不会注册它们）: {missing_in_manifest}"
    )
    assert not missing_seed_files, f"manifest 声明了不存在的种子文件: {missing_seed_files}"


def test_every_seed_definition_parses_and_matches_id() -> None:
    for path in sorted(_seed_dir().glob("*.json")):
        definition = ScheduledTask.model_validate_json(path.read_text(encoding="utf-8"))
        assert definition.task_id == path.stem, f"task_id 与文件名不一致: {path.name}"
        # 定时触发的任务必须有可解析的调度配置
        if definition.trigger_type == "schedule":
            assert definition.schedule_type, f"缺少 schedule_type: {path.name}"
