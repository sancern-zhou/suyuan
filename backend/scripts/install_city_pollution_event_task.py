"""
Install a scheduled Agent task for city pollution event monitoring.

The task uses the existing scheduled task system. At each interval the Agent is
asked to call city_pollution_event_monitor, then apply the analysis skill to any
generated evidence packs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _parse_cities(value: str) -> List[str]:
    cities = [item.strip() for item in value.split(",") if item.strip()]
    if not cities:
        raise SystemExit("At least one city is required.")
    return cities


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value, flags=re.UNICODE).strip("_")
    return slug or "city"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install city pollution event monitor scheduled task.")
    parser.add_argument("--cities", required=True, help="Comma-separated city list, e.g. 广州,佛山")
    parser.add_argument("--interval-minutes", type=int, default=30, help="Run interval in minutes. Default: 30")
    parser.add_argument("--hours", type=int, default=24, help="Lookback hours. Default: 24")
    parser.add_argument("--station-type", default="国控", help="Station type. Default: 国控")
    parser.add_argument("--enabled", action="store_true", help="Create enabled task. Default is disabled.")
    parser.add_argument("--replace", action="store_true", help="Replace existing task with the same deterministic ID.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from app.scheduled_tasks.models import ScheduledTask, ScheduleType
    from app.scheduled_tasks.storage import TaskStorage

    cities = _parse_cities(args.cities)
    city_label = "_".join(_safe_slug(city) for city in cities)
    task_id = f"task_city_pollution_event_monitor_{city_label}"
    storage = TaskStorage()

    existing = storage.get(task_id)
    if existing and not args.replace:
        print(json.dumps({
            "success": False,
            "message": f"Task already exists: {task_id}. Use --replace to overwrite.",
        }, ensure_ascii=False, indent=2))
        return 1
    if existing and args.replace:
        storage.delete(task_id)

    prompt = f"""
执行城市污染过程识别告警任务。

1. 必须先调用 city_pollution_event_monitor 工具，参数：
   - cities={cities!r}
   - hours={args.hours}
   - station_type="{args.station_type}"
   - force_collect=false
   - include_components=true
2. 如果工具返回 event_artifacts：
   - 逐个读取 event_artifacts[].evidence_pack。
   - 读取技能文档 backend/docs/skills/city_pollution_process_analysis.md。
   - 按技能要求提出假设、验证支持证据和反证、说明数据质量影响。
   - 在 evidence_pack 同目录写入 reasoning_analysis.md。
3. 如果没有事件，只总结数据质量状态和本轮未触发告警原因。
4. 最终回复必须包含：检测城市、事件数量、证据包路径、分析文件路径、最高优先级建议。
""".strip()

    task = ScheduledTask(
        task_id=task_id,
        name="城市污染过程告警",
        description=f"每{args.interval_minutes}分钟巡检 {', '.join(cities)} 最近{args.hours}小时污染过程并触发Agent分析",
        schedule_type=ScheduleType.INTERVAL,
        enabled=bool(args.enabled),
        interval_minutes=args.interval_minutes,
        prompt=prompt,
        timeout_seconds=1800,
        tags=["pollution_event_monitor", "city_process", "auto_analysis"],
    )
    storage.create(task)

    print(json.dumps({
        "success": True,
        "task_id": task.task_id,
        "enabled": task.enabled,
        "interval_minutes": task.interval_minutes,
        "message": "Task installed. If the backend is already running, restart it or create the task through the API so the scheduler picks it up immediately.",
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
