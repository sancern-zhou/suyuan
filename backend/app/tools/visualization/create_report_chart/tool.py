from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.visualization.create_report_chart.renderer import ChartDataError


REFERENCE_DIR = Path(__file__).resolve().parent / "references"


def report_chart_reference_paths() -> Dict[str, str]:
    return {
        "index": str(REFERENCE_DIR / "index.md"),
        "word_a4_rules": str(REFERENCE_DIR / "word-a4-rules.md"),
        "layout_rules": str(REFERENCE_DIR / "layout-rules.md"),
        "long_label_rules": str(REFERENCE_DIR / "long-label-rules.md"),
        "pie_rules": str(REFERENCE_DIR / "pie-rules.md"),
        "chart_types": str(REFERENCE_DIR / "chart-types.md"),
        "bar_chart": str(REFERENCE_DIR / "bar-chart.md"),
        "line_chart": str(REFERENCE_DIR / "line-chart.md"),
        "scatter_chart": str(REFERENCE_DIR / "scatter-chart.md"),
        "stacked_area": str(REFERENCE_DIR / "stacked-area.md"),
        "dual_axis_line": str(REFERENCE_DIR / "dual-axis-line.md"),
        "stacked_bar": str(REFERENCE_DIR / "stacked-bar.md"),
        "histogram": str(REFERENCE_DIR / "histogram.md"),
        "correlation_heatmap": str(REFERENCE_DIR / "correlation-heatmap.md"),
        "boxplot": str(REFERENCE_DIR / "boxplot.md"),
        "table_image": str(REFERENCE_DIR / "table-image.md"),
        "pollutant_calendar": str(REFERENCE_DIR / "pollutant-calendar.md"),
        "generic_pollutant_wind_rose": str(REFERENCE_DIR / "generic-pollutant-wind-rose.md"),
        "aqi_calendar": str(REFERENCE_DIR / "aqi-calendar.md"),
        "pollutant_wind_rose": str(REFERENCE_DIR / "pollutant-wind-rose.md"),
    }


class CreateReportChartTool(LLMTool):
    """Create static report charts for QMD/Word output."""

    def __init__(self):
        reference_paths = report_chart_reference_paths()
        description = (
            "创建正式报告静态图表；先读 references/index.md="
            f"{reference_paths['index']}，再按图型读取规则。"
        )
        function_schema = {
            "name": "create_report_chart",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_id": {
                        "type": "string",
                        "description": "图表ID；可选，不提供时自动生成。",
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": [
                            "bar",
                            "horizontal_bar",
                            "line",
                            "timeseries",
                            "scatter",
                            "pie",
                            "stacked_area",
                            "dual_axis_line",
                            "stacked_bar",
                            "percent_stacked_bar",
                            "histogram",
                            "correlation_heatmap",
                            "boxplot",
                            "table_image",
                            "pollutant_calendar",
                            "generic_pollutant_wind_rose",
                            "aqi_calendar",
                            "pollutant_wind_rose",
                        ],
                        "description": "图表类型。",
                    },
                    "title": {"type": "string", "description": "图表标题。"},
                    "data": {
                        "type": "object",
                        "description": (
                            "结构化图表数据，不是 ECharts option。"
                            "line/bar/pie 推荐传 labels+values 或 x+y；"
                            "单序列可传 series[0].data 或 series[0].values。"
                            "line/bar 支持多序列 series，每个序列使用 name + data/values。"
                            "使用 data_id 时，数据应已保存为上述图表数据对象。"
                        ),
                    },
                    "data_id": {
                        "type": "string",
                        "description": "上游数据引用ID；与 data 二选一。",
                    },
                    "output_context": {
                        "type": "string",
                        "enum": ["word", "screen", "html"],
                        "description": "输出载体，正式报告默认 word。",
                    },
                    "style_profile": {
                        "type": "string",
                        "enum": ["report", "compact", "presentation"],
                        "description": "视觉密度配置，默认 report。",
                    },
                    "notes": {
                        "type": "string",
                        "description": "图表意图、单位或口径。",
                    },
                    "options": {
                        "type": "object",
                        "description": (
                            "少量图型参数；支持 x_label、y_label、unit、legend、reference_lines。"
                            "reference_lines 示例：[{axis:'y', value:100, label:'参考线'}]。"
                            "复杂视觉规则请先读取引用文档。"
                        ),
                    },
                },
                "required": ["chart_type", "title"],
            },
        }
        super().__init__(
            name="create_report_chart",
            description=description,
            category=ToolCategory.VISUALIZATION,
            function_schema=function_schema,
            version="0.1.0",
            requires_context=True,
        )

    async def execute(
        self,
        context: Optional[Any] = None,
        chart_type: str = "",
        title: str = "",
        chart_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        data_id: Optional[str] = None,
        output_context: str = "word",
        style_profile: str = "report",
        notes: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        opts = dict(options or {})
        metadata = {
            "tool_name": self.name,
            "schema_version": "report_chart.v1",
            "chart_type": chart_type,
            "output_context": output_context or "word",
            "style_profile": style_profile or "report",
            "reference_paths": report_chart_reference_paths(),
        }
        if opts.get("dry_run"):
            return {
                "success": True,
                "status": "success",
                "metadata": metadata,
                "data": {
                    "chart_id": chart_id,
                    "chart_type": chart_type,
                    "title": title,
                    "render_mode": "dry_run",
                    "data_id": data_id,
                    "has_inline_data": data is not None,
                    "notes": notes,
                },
                "summary": "报告图表请求已按 create_report_chart 统一入口解析；dry_run 未生成图片。",
            }

        try:
            chart_data = self._resolve_chart_data(data=data, data_id=data_id, context=context)

            from app.tools.visualization.create_report_chart.renderer import render_report_chart

            rendered = render_report_chart(
                chart_id=chart_id,
                chart_type=chart_type,
                title=title,
                data=chart_data,
                output_context=output_context or "word",
                style_profile=style_profile or "report",
                options=opts,
            )
            metadata.update(rendered.get("metadata", {}))
            if data_id:
                metadata["source_data_id"] = data_id
            return {
                "success": True,
                "status": "success",
                "metadata": metadata,
                "data": rendered,
                "visuals": rendered.get("visuals", []),
                "summary": rendered.get("summary", "报告图表已生成。"),
            }
        except ChartDataError as exc:
            return self._failed_result(str(exc), metadata, chart_type, title, data_id)
        except (KeyError, ValueError, TypeError) as exc:
            return self._failed_result(str(exc), metadata, chart_type, title, data_id)

    def _resolve_chart_data(
        self,
        data: Optional[Dict[str, Any]],
        data_id: Optional[str],
        context: Optional[Any],
    ) -> Dict[str, Any]:
        if data is not None:
            return data
        if not data_id:
            return {}
        if context is None:
            raise ChartDataError("使用 data_id 调用 create_report_chart 需要 ExecutionContext。")

        try:
            loaded = context.get_raw_data(data_id)
        except AttributeError as exc:
            raise ChartDataError("当前上下文不支持 get_raw_data，无法读取 data_id。") from exc

        return self._normalize_loaded_chart_data(loaded, data_id)

    def _normalize_loaded_chart_data(self, loaded: Any, data_id: str) -> Dict[str, Any]:
        if isinstance(loaded, dict):
            return loaded
        if isinstance(loaded, list) and len(loaded) == 1:
            first = loaded[0]
            if isinstance(first, dict):
                if isinstance(first.get("data"), dict):
                    return dict(first["data"])
                return dict(first)
            if isinstance(first, list) and all(isinstance(item, dict) for item in first):
                return {"records": first}
        if isinstance(loaded, list) and all(isinstance(item, dict) for item in loaded):
            return {"records": loaded}
        raise ChartDataError(
            f"data_id {data_id} 未保存为 create_report_chart 可直接使用的图表数据对象；"
            "请先整理为 labels+values、x+y 或单序列 series 数据。"
        )

    def _failed_result(
        self,
        error: str,
        metadata: Dict[str, Any],
        chart_type: str,
        title: str,
        data_id: Optional[str],
    ) -> Dict[str, Any]:
        if data_id:
            metadata["source_data_id"] = data_id
        return {
            "success": False,
            "status": "failed",
            "error": error,
            "metadata": metadata,
            "data": {
                "chart_type": chart_type,
                "title": title,
                "data_id": data_id,
            },
            "visuals": [],
            "summary": f"报告图表生成失败：{error}",
        }
