"""
Install a scheduled Agent task for hourly air quality data quality monitoring.
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
    parser = argparse.ArgumentParser(description="Install hourly air quality data quality monitor scheduled task.")
    parser.add_argument("--cities", required=True, help="Comma-separated city list, e.g. 广州,佛山")
    parser.add_argument("--interval-minutes", type=int, default=60, help="Run interval in minutes. Default: 60")
    parser.add_argument("--hours", type=int, default=24, help="Lookback hours. Default: 24")
    parser.add_argument("--station-type", default="国控", help="Station type. Default: 国控")
    parser.add_argument("--enabled", action="store_true", help="Create enabled task. Default is disabled.")
    parser.add_argument("--replace", action="store_true", help="Replace existing task with the same deterministic ID.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from app.scheduled_tasks.models import ScheduledTask, ScheduleType, TaskStep
    from app.scheduled_tasks.storage import TaskStorage

    cities = _parse_cities(args.cities)
    city_label = "_".join(_safe_slug(city) for city in cities)
    task_id = f"task_air_quality_data_quality_monitor_{city_label}"
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
执行空气质量监测数据质量自动巡检任务。

1. 必须先调用 air_quality_data_quality_monitor 工具，参数：
   - cities={cities!r}
   - hours={args.hours}
   - station_type="{args.station_type}"
2. 如果工具返回 issue_packages：
   - 逐个读取 issue_packages[].quality_package。
   - 读取技能文档 backend/docs/skills/air_quality_data_quality_analysis.md。
   - 按技能要求核查规则命中、真实污染反证、仪器/质控/维护可能性。
   - 在 quality_package 同目录写入 data_quality_analysis.md。
3. 如果没有 issue_packages，不需要写分析文件，只说明本轮未发现疑似数据质量问题，且干净数据已舍弃。
4. 最终回复必须包含：检测城市、疑似问题数量、问题包路径、最高优先级处置建议。
""".strip()

    task = ScheduledTask(
        task_id=task_id,
        name="空气质量数据质量巡检",
        description=f"每{args.interval_minutes}分钟巡检 {', '.join(cities)} 最近{args.hours}小时站点数据质量",
        schedule_type=ScheduleType.INTERVAL,
        enabled=bool(args.enabled),
        interval_minutes=args.interval_minutes,
        steps=[
            TaskStep(
                step_id="detect_and_analyze_data_quality",
                description="识别疑似数据质量问题并生成自动分析",
                agent_prompt=prompt,
                timeout_seconds=1800,
                retry_on_failure=True,
            )
        ],
        tags=["data_quality_monitor", "air_quality", "auto_analysis"],
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
