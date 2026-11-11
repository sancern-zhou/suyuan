"""推送共享层单元测试：受众组解析、微信队列通用入队、episode 兜底读取。"""

from __future__ import annotations

import json

from app.scenarios.xuchang_push_common import audiences
from app.scenarios.xuchang_push_common.episodes import load_episodes_between
from app.scenarios.xuchang_station_deviation import wechat_push_queue as queue
from datetime import date


def test_resolve_audience_accounts_defaults_kept_when_no_override(tmp_path, monkeypatch):
    monkeypatch.delenv(audiences.AUDIENCES_FILE_ENV, raising=False)
    resolved = audiences.resolve_audience_accounts(
        ["科长"], registry_root=tmp_path,
        audiences=audiences.load_push_audiences(tmp_path),
    )
    # 默认科长挂大气科1-4
    assert resolved == [
        "app:android:大气科1", "app:android:大气科2",
        "app:android:大气科3", "app:android:大气科4",
    ]


def test_resolve_audience_accounts_override_file(tmp_path, monkeypatch):
    monkeypatch.delenv(audiences.AUDIENCES_FILE_ENV, raising=False)
    (tmp_path / audiences.AUDIENCES_FILE_NAME).write_text(
        json.dumps({
            "局长": {"app_accounts": ["bureau-chief"]},
            "执法": {"app_accounts": ["zhifa1", "zhifa1", "zhifa2"]},
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    catalog = audiences.load_push_audiences(tmp_path)
    assert audiences.resolve_audience_accounts(["局长"], audiences=catalog) == [
        "app:android:bureau-chief"
    ]
    # 去重保序 + 多角色合并
    assert audiences.resolve_audience_accounts(
        ["局长", "执法"], audiences=catalog
    ) == [
        "app:android:bureau-chief",
        "app:android:zhifa1",
        "app:android:zhifa2",
    ]


def test_resolve_audience_accounts_unknown_and_empty_roles_skipped(tmp_path):
    catalog = audiences.load_push_audiences(tmp_path)
    assert audiences.resolve_audience_accounts(["局长"], audiences=catalog) == []
    assert audiences.resolve_audience_accounts(["不存在的角色"], audiences=catalog) == []
    assert audiences.resolve_audience_accounts("", audiences=catalog) == []


def test_env_override_path(tmp_path, monkeypatch):
    override = tmp_path / "custom-audiences.json"
    override.write_text(
        json.dumps({"驻场": {"app_accounts": ["zhuchang1"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv(audiences.AUDIENCES_FILE_ENV, str(override))
    catalog = audiences.load_push_audiences(tmp_path / "nonexistent-registry")
    assert catalog["驻场"]["app_accounts"] == ["zhuchang1"]


def test_enqueue_wechat_message_generic(tmp_path):
    record = queue.enqueue_wechat_message(
        "pollution_cause",
        "【污染原因分析】正文",
        media=[],
        metadata={"target_date": "2026-11-10", "empty_field": None},
        root=tmp_path,
    )
    assert record["kind"] == "pollution_cause"
    assert record["text"].startswith("【污染原因分析】")
    assert record["metadata"] == {"target_date": "2026-11-10"}
    stored = json.loads(
        (tmp_path / queue.QUEUE_DIR_NAME / queue.PENDING_DIR / f"{record['id']}.json")
        .read_text(encoding="utf-8")
    )
    assert stored == record


def test_enqueue_wechat_message_empty_text_skipped(tmp_path):
    assert queue.enqueue_wechat_message("kind", "  ", root=tmp_path) is None


def test_station_alert_enqueue_wraps_generic(tmp_path):
    record = queue.enqueue_station_alert_wechat_message(
        {"station_id": "1008A", "station_name": "许昌学院", "alerts": []},
        "通报正文",
        root=tmp_path,
    )
    assert record["kind"] == "station_alert"
    assert record["metadata"]["station_id"] == "1008A"


def test_load_episodes_between_state_file_fallback(tmp_path, monkeypatch):
    import app.scenarios.xuchang_push_common.episodes as episodes_module

    state_path = tmp_path / "xuchang_station_deviation_alerts" / "episode_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "active": [],
        "history": [
            {"episode_id": "ep-1", "started_at": "2026-11-05T09:00:00",
             "station_id": "1008A", "station_name": "许昌学院",
             "target_pollutant": "PM10", "peak_station_value": 120.0},
            {"episode_id": "ep-out", "started_at": "2026-10-01T09:00:00"},
            {"episode_id": "ep-bad", "started_at": "not-a-date"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(episodes_module, "get_data_registry", lambda: tmp_path)
    monkeypatch.setattr(
        episodes_module, "_query_episodes_db", lambda start, end: None
    )
    episodes = load_episodes_between(date(2026, 11, 1), date(2026, 12, 1))
    assert [item["episode_id"] for item in episodes] == ["ep-1"]
