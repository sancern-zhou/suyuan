"""Generate a visual review gallery for the analytical report chart expansion."""

from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from app.tools.visualization.create_report_chart.tool import CreateReportChartTool

CASES = {
    "combo": (
        {
            "labels": ["一季度", "二季度", "三季度", "四季度"],
            "series": [
                {"name": "产量", "type": "bar", "values": [120, 150, 180, 210]},
                {
                    "name": "增长率",
                    "type": "line",
                    "axis": "right",
                    "values": [8.2, 12.5, 9.6, 15.1],
                },
            ],
        },
        {"left_y_label": "产量（吨）", "right_y_label": "增长率（%）"},
    ),
    "range_line": (
        {
            "labels": ["一月", "二月", "三月", "四月"],
            "series": [
                {
                    "name": "月均浓度",
                    "values": [42, 38, 35, 37],
                    "lower": [35, 31, 29, 30],
                    "upper": [49, 45, 42, 46],
                }
            ],
        },
        {"y_label": "浓度", "unit": "μg/m³"},
    ),
    "waterfall": (
        {
            "labels": ["结构调整", "产量变化", "阶段小计", "治理措施"],
            "values": [-12, 8, 96, -6],
            "measures": ["relative", "relative", "subtotal", "relative"],
            "start_value": 100,
        },
        {"y_label": "排放量", "unit": "吨"},
    ),
    "pareto": (
        {"labels": ["工业源", "移动源", "扬尘源", "生活源"], "values": [45, 30, 15, 10]},
        {"y_label": "贡献量"},
    ),
    "diverging_bar": (
        {"labels": ["城市A", "城市B", "城市C", "城市D"], "values": [-8.2, 3.1, -1.5, 5.4]},
        {"unit": "%"},
    ),
    "step_line": (
        {"labels": ["阶段一", "阶段二", "阶段三", "阶段四"], "values": [35, 50, 40, 30]},
        {"step": "post", "y_label": "标准限值"},
    ),
    "error_bar": (
        {
            "labels": ["A组", "B组", "C组", "D组"],
            "series": [
                {"name": "均值", "values": [12, 15, 11, 14], "errors": [1.2, 1.5, 0.8, 1.1]}
            ],
        },
        {"y_label": "测量结果"},
    ),
}


async def generate(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tool = CreateReportChartTool()
    for output_context in ("word", "screen"):
        for chart_type, (data, options) in CASES.items():
            result = await tool.execute(
                chart_id=f"gallery_{output_context}_{chart_type}",
                chart_type=chart_type,
                title=f"{chart_type} 示例",
                data=data,
                options=options,
                output_context=output_context,
            )
            if not result.get("success"):
                raise RuntimeError(result.get("error") or f"{chart_type} render failed")
            source = Path(result["visuals"][0]["local_path"])
            destination = output_dir / f"{output_context}_{chart_type}.png"
            shutil.copy2(source, destination)
            print(destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/create_report_chart_gallery"))
    args = parser.parse_args()
    asyncio.run(generate(args.output_dir))


if __name__ == "__main__":
    main()
