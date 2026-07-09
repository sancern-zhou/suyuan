from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def parse_hour(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class EvidenceRunPaths:
    run_dir: Path
    alert_path: Path


def _format_capture_timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%d_%H%M%S")


def build_evidence_run_paths(registry_root: Path, captured_at: datetime) -> EvidenceRunPaths:
    timestamp = _format_capture_timestamp(captured_at)
    run_dir = (
        registry_root
        / "scenarios"
        / "yuncheng_trial"
        / captured_at.strftime("%Y%m")
        / timestamp
    )
    return EvidenceRunPaths(
        run_dir=run_dir,
        alert_path=run_dir / f"{timestamp}_alert.json",
    )


def build_alert_run_dir(registry_root: Path, target_time: str) -> Path:
    """Backward-compatible lookup for older evidence directories."""
    dt = parse_hour(target_time)
    return (
        registry_root
        / "scenarios"
        / "yuncheng_trial"
        / dt.strftime("%Y%m%d")
        / dt.strftime("%H%M")
    )
