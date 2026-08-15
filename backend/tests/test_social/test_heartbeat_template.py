from app.social.heartbeat_service import HeartbeatService


def test_default_heartbeat_file_does_not_include_sample_tasks(tmp_path):
    service = HeartbeatService(workspace=tmp_path, interval_s=3600)

    content = service.heartbeat_file.read_text(encoding="utf-8")

    assert "每日空气质量报告" not in content
    assert "PM2.5超标监控" not in content
    assert "## 示例任务" not in content
