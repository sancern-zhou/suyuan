# -*- coding: utf-8 -*-
"""源码修复授权测试（tag/白名单/敏感面/快照）。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.tools.runtime_monitor import repair_auth


def _ctx(tags=None, execution_id="e1"):
    return SimpleNamespace(
        scheduled_task_context={"task_id": "t1", "execution_id": execution_id},
        runtime_metadata={"scheduled_task": {"tags": tags or []}},
    )


@pytest.fixture()
def whitelist(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(
        settings, "source_repair_allowed_dirs", "backend/app/fetchers,backend/app/tools"
    )
    return settings


@pytest.fixture()
def snapshot_ok(monkeypatch):
    async def fake_get_or_create(execution_id):
        return f"snap-{execution_id}"

    monkeypatch.setattr(repair_auth, "_get_or_create_snapshot", fake_get_or_create)


def _repo_path(rel):
    from app.utils.path_config import PROJECT_ROOT

    return str(PROJECT_ROOT / rel)


def test_denied_without_tag(whitelist, snapshot_ok):
    ok, note, _ = asyncio.run(
        repair_auth.ensure_source_repair_authorized(
            _ctx(tags=["runtime-monitor"]), _repo_path("backend/app/fetchers/x.py")
        )
    )
    assert ok is False and "source-repair" in note


def test_denied_outside_whitelist(whitelist, snapshot_ok):
    ok, note, _ = asyncio.run(
        repair_auth.ensure_source_repair_authorized(
            _ctx(tags=["source-repair"]), _repo_path("backend/app/api/agent.py")
        )
    )
    assert ok is False and "白名单" in note


def test_hard_denied_sensitive_paths(whitelist, snapshot_ok):
    # 即使把 config 塞进白名单，敏感面依旧硬拒绝
    from config.settings import settings

    settings.source_repair_allowed_dirs = "backend/config"
    ok, note, _ = asyncio.run(
        repair_auth.ensure_source_repair_authorized(
            _ctx(tags=["source-repair"]), _repo_path("backend/config/settings.py")
        )
    )
    assert ok is False and "敏感" in note


def test_authorized_in_whitelist_with_snapshot(whitelist, snapshot_ok):
    ok, note, snap = asyncio.run(
        repair_auth.ensure_source_repair_authorized(
            _ctx(tags=["source-repair"]), _repo_path("backend/app/fetchers/tenders/x.py")
        )
    )
    assert ok is True and snap == "snap-e1"


def test_denied_without_snapshot(whitelist, monkeypatch):
    async def none(execution_id):
        return None

    monkeypatch.setattr(repair_auth, "_get_or_create_snapshot", none)
    ok, note, _ = asyncio.run(
        repair_auth.ensure_source_repair_authorized(
            _ctx(tags=["source-repair"]), _repo_path("backend/app/fetchers/x.py")
        )
    )
    assert ok is False and "快照" in note


def test_empty_whitelist_disables_everything(snapshot_ok, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "source_repair_allowed_dirs", "")
    ok, note, _ = asyncio.run(
        repair_auth.ensure_source_repair_authorized(
            _ctx(tags=["source-repair"]), _repo_path("backend/app/fetchers/x.py")
        )
    )
    assert ok is False and "白名单" in note
