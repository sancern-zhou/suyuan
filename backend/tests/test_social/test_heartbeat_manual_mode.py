from pathlib import Path

from app.social.heartbeat_service import HeartbeatService


def test_heartbeat_parser_preserves_manual_mode(tmp_path: Path):
    heartbeat_file = tmp_path / "HEARTBEAT.md"
    heartbeat_file.write_text(
        """
- name: ops task
  schedule: "10 * * * *"
  manual_mode: ops
  description: Run an ops workflow.
  enabled: true
  channels: ['ops']
  next_run_at: "2026-07-01T17:10:00+08:00"
""",
        encoding="utf-8",
    )

    service = HeartbeatService(workspace=tmp_path, user_id="ops:system:test")
    tasks = service._parse_tasks(heartbeat_file.read_text(encoding="utf-8"))

    assert len(tasks) == 1
    assert tasks[0]["manual_mode"] == "ops"
    assert tasks[0]["schedule"] == "10 * * * *"
