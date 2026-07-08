from datetime import datetime
from pathlib import Path


def parse_hour(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def build_alert_run_dir(registry_root: Path, target_time: str) -> Path:
    dt = parse_hour(target_time)
    return (
        registry_root
        / "scenarios"
        / "yuncheng_trial"
        / dt.strftime("%Y%m%d")
        / dt.strftime("%H%M")
    )
