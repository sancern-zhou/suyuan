"""微信群推送文件队列单元测试：入队提取、顺序、归档清理。"""

from __future__ import annotations

import json
import os
import time

import pytest

from app.scenarios.xuchang_station_deviation import wechat_push_queue as queue


def _package(alerts=(), station_id="1008A", station_name="许昌学院"):
    return {
        "station_id": station_id,
        "station_name": station_name,
        "alerts": list(alerts),
    }


def _alert(pollutant="PM10", episode_id="ep-1"):
    return {
        "alert": {
            "target_pollutant": pollutant,
            "scenario_1_episode": {"episode_id": episode_id},
        }
    }


def _status_path(tmp_path, status):
    return tmp_path / queue.QUEUE_DIR_NAME / status


def test_enqueue_extracts_episode_and_pollutants(tmp_path):
    record = queue.enqueue_station_alert_wechat_message(
        _package([_alert("PM10", "ep-a"), _alert("SO2", "ep-a")]),
        "通报正文",
        root=tmp_path,
    )

    assert record is not None
    assert record["kind"] == "station_alert"
    assert record["metadata"]["episode_id"] == "ep-a"
    assert record["metadata"]["pollutants"] == "PM10、SO2"
    assert record["metadata"]["station_name"] == "许昌学院"
    assert record["attempts"] == 0
    stored = json.loads(
        (_status_path(tmp_path, queue.PENDING_DIR) / f"{record['id']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["text"] == "通报正文"


def test_enqueue_without_episode_or_alerts_still_queues(tmp_path):
    record = queue.enqueue_station_alert_wechat_message(
        _package(), "正文", root=tmp_path
    )
    assert record["metadata"]["episode_id"] == ""
    assert record["metadata"]["pollutants"] == ""


def test_list_pending_orders_by_enqueue_time_and_skips_broken_file(tmp_path):
    first = queue.enqueue_station_alert_wechat_message(_package(), "第一条", root=tmp_path)
    second = queue.enqueue_station_alert_wechat_message(_package(), "第二条", root=tmp_path)
    broken = _status_path(tmp_path, queue.PENDING_DIR) / "wx-broken.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{not-json", encoding="utf-8")

    messages = queue.list_pending_messages(root=tmp_path)

    assert [m["id"] for m in messages] == [first["id"], second["id"]]
    assert queue.list_pending_messages(limit=1, root=tmp_path)[0]["id"] == first["id"]


def test_ack_unknown_and_invalid_ids(tmp_path):
    assert queue.ack_message("wx-none", "sent", root=tmp_path) == "unknown"
    with pytest.raises(ValueError):
        queue.ack_message("../escape", "sent", root=tmp_path)
    with pytest.raises(ValueError):
        queue.ack_message("wx-1", "maybe", root=tmp_path)


def test_cleanup_archive_keeps_recent_files(tmp_path):
    record = queue.enqueue_station_alert_wechat_message(_package(), "正文", root=tmp_path)
    queue.ack_message(record["id"], "sent", root=tmp_path)
    archived = _status_path(tmp_path, queue.SENT_DIR) / f"{record['id']}.json"
    old_stamp = time.time() - 30 * 86400
    os.utime(archived, (old_stamp, old_stamp))

    removed = queue.cleanup_archive(keep_days=7, root=tmp_path)

    assert removed == 1
    assert not archived.exists()
