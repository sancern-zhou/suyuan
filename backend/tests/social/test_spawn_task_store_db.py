# -*- coding: utf-8 -*-
"""spawn 任务存储：PostgreSQL 默认 + JSON 显式回退测试。"""
import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.social.task_status_store import TaskStatusStore


@pytest.fixture()
def db_factory(tmp_path):
    """独立 sqlite 库 + 只建 spawn_tasks 表。

    不能用 Base.metadata.create_all：同一 Base 上的其他模型含 PostgreSQL
    专属类型（JSONB），sqlite 无法渲染。
    """
    from app.db.models.spawn_task_db import SpawnTaskDB

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'spawn.db'}", poolclass=NullPool
    )

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(SpawnTaskDB.__table__.create, checkfirst=True)

    asyncio.run(_prepare())
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _record(task_id="spawn_task_1", owner="web:assistant:zhangsan", status="pending"):
    return {
        "task_id": task_id,
        "social_user_id": owner,
        "task": "写一首诗",
        "label": "诗歌",
        "status": status,
        "progress": 0.0,
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "origin_channel": "web",
        "origin_chat_id": "zhangsan",
        "origin_sender_id": "zhangsan",
        "bot_account": "assistant",
    }


def test_db_storage_roundtrip(db_factory):
    engine, factory = db_factory
    store = TaskStatusStore(db_manager=factory)
    assert store._use_json is False

    async def _run():
        await store.create_task(
            social_user_id="web:assistant:zhangsan",
            task="写一首诗",
            label="诗歌",
            origin_channel="web",
            origin_chat_id="zhangsan",
            origin_sender_id="zhangsan",
            bot_account="assistant",
        )
        user_tasks = await store.get_user_tasks("web:assistant:zhangsan")
        assert len(user_tasks) == 1
        task_id = user_tasks[0]["task_id"]
        # 状态更新跨会话可见（模拟另一进程读）
        await store.update_task(task_id, status="completed", progress=1.0, result="诗句")
        fresh = TaskStatusStore(db_manager=factory)
        got = await fresh.get_task(task_id)
        assert got["status"] == "completed"
        assert got["result"] == "诗句"
        # 归属隔离
        assert await fresh.get_user_tasks("web:assistant:lisi") == []

    asyncio.run(_run())
    asyncio.run(engine.dispose())


def test_explicit_json_fallback(tmp_path):
    store = TaskStatusStore(db_manager=False, json_path=str(tmp_path / "tasks.json"))
    assert store._use_json is True

    async def _run():
        await store.create_task(
            social_user_id="weixin:default:chat1",
            task="任务",
            origin_channel="weixin",
            origin_chat_id="chat1",
            origin_sender_id="chat1",
        )
        tasks = await store.get_user_tasks("weixin:default:chat1")
        assert len(tasks) == 1

    asyncio.run(_run())


def test_default_resolves_project_session_factory():
    """默认构造应解析到项目 session 工厂（可用环境），而非静默退回 JSON。"""
    store = TaskStatusStore()
    # 容器/正常开发环境都能导入 session_async_session
    assert store._use_json is False
    assert store.db_manager is not None
