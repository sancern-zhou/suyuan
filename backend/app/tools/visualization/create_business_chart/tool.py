from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import file_products, resources_for_visuals
from app.tools.resource_refs import build_data_file_ref, build_file_ref, build_visual_ref, merge_refs
from app.tools.visualization.create_business_chart.renderer import ChartDataError, SPECIALIZED_CHART_TYPES
from app.utils.path_config import format_agent_path


REFERENCE_DIR = Path(__file__).resolve().parent / "references"


def business_chart_reference_paths() -> Dict[str, str]:
    paths = {
        "index": str(REFERENCE_DIR / "index.md"),
        "pollutant_calendar": str(REFERENCE_DIR / "pollutant-calendar.md"),
        "generic_pollutant_wind_rose": str(REFERENCE_DIR / "generic-pollutant-wind-rose.md"),
        "wind_timeseries": str(REFERENCE_DIR / "wind-timeseries.md"),
        "weather_timeseries": str(REFERENCE_DIR / "weather-timeseries.md"),
        "aqi_calendar": str(REFERENCE_DIR / "aqi-calendar.md"),
        "pollutant_wind_rose": str(REFERENCE_DIR / "pollutant-wind-rose.md"),
    }
    return {name: format_agent_path(path) for name, path in paths.items()}


class CreateBusinessChartTool(LLMTool):
    """Create static charts for documented business scenarios."""

    def __init__(self):
        reference_paths = business_chart_reference_paths()
        description = (
            "业务图表工具：绘制特定业务图型和固定模板（风玫瑰、污染日历、气象时序等），支持已有预定义图型。"
            "匹配本工具已支持的专用业务图型时，所有模式必须使用 create_business_chart，禁止用 Python/ECharts 重绘替代；"
            "此规则优先于模式默认工具。其他通用/自定义图表：问数模式主要使用 execute_echarts_python，专家/报告模式主要使用 execute_python。"
            f"采用两层规范：先读公共入口 references/index.md={reference_paths['index']}，"
            "再且仅按选定 chart_type 读取一份对应图型文档；无需另读输入、A4 或布局规范。"
            "必须通过 data 或 file_path 至少提供一种数据输入。"
            "仅支持污染物/AQI 日历、污染物风玫瑰、风场污染物叠加时序和气象五要素时序。"
            "常规柱状、折线、散点、饼图、分布、热力图及自定义组合图不由本工具绘制；"
            "问数交互图使用 execute_echarts_python，静态分析及报告图使用 execute_python。"
            "weather_timeseries 绘制连续 1–7 天风向、风速、温度、降水概率、湿度五要素，禁止叠加污染物或重叠不同日期曲线；"
            "气象背景叠加污染物使用 wind_timeseries；纯风向频率图使用 Python，不得用占位浓度制作污染物风玫瑰。"
            "现成业务图可作为组合报告素材复用；尚未覆盖的自定义分析、分面、多子图和科研图表使用 execute_python + matplotlib/seaborn。"
            "生成的静态图在对话正文展示，不进入右侧交互图面板；"
            "单独交付图表时可在最终答复中用 [[chart:<visual_id>]] 控制位置，visual_id 取返回的 visuals.id，"
            "未指定位置的图由前端追加到本轮答复末尾。制作正式报告时图表仍可作为报告素材复用，"
            "报告包内部配图不会自动逐张追加到对话。不要自行拼图片 URL 或本地路径。"
        )
        function_schema = {
            "name": "create_business_chart",
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
                        "enum": sorted(SPECIALIZED_CHART_TYPES),
                        "description": "业务场景图型，仅支持列出的专用类型。",
                    },
                    "title": {"type": "string", "description": "图表标题。"},
                    "data": {
                        "type": "object",
                        "description": (
                            "结构化图表数据，不是 ECharts option。"
                            "按对应业务图型文档提供 records、日期与污染物浓度数组、风向风速与真实浓度数组等。"
                            "输入必须符合选定图型的业务口径；不接收常规图型或 charts 嵌套多图请求。"
                            "与 file_path 同时提供时，data 用于渲染，file_path 仅用于来源追踪。"
                        ),
                    },
                    "file_path": {
                        "type": "string",
                        "description": (
                            "仅接受本轮会话上游工具返回的已授权数据 file_path，必须逐字原样复用返回值；"
                            "不得自行构造、猜测或改写存储路径。"
                            "execute_python 产生的结构化数据必须先通过 save_data(...) 保存，"
                            "此处只能传入 save_data 返回的 file_path，不能传入执行环境内自行写入的中间路径。"
                            "未提供 data 时，工具通过 ExecutionContext 自动读取，"
                            "Agent 无需调用 get_raw_data；数据资产应符合目标业务图型契约。"
                            "与 data 同时提供时仅用于来源追踪。"
                        ),
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
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                        "description": "图表意图、单位或口径。",
                    },
                    "options": {
                        "type": "object",
                        "description": (
                            "专用图型参数，以对应业务文档为准；污染物风玫瑰支持字段映射、方向分箱和风速分箱。"
                            "wind_timeseries 使用风速/风向角时必须显式提供 "
                            "wind_direction_convention（meteorological_from 或 mathematical_to）；"
                            "直接提供 east_u/north_v 时无需该参数。"
                            "reference_lines 示例：[{axis:'y', value:100, label:'参考线'}]。"
                            "line_width 可传正数控制折线宽度；weather_timeseries 支持 records、"
                            "areas/risk_periods 及 time_field/wind_speed_field/wind_direction_degrees_field/"
                            "temperature_field/precipitation_probability_field/humidity_field。"
                            "复杂视觉规则请先读取引用文档。"
                        ),
                    },
                },
                "required": ["chart_type", "title"],
                "anyOf": [
                    {"required": ["data"]},
                    {"required": ["file_path"]},
                ],
            },
        }
        super().__init__(
            name="create_business_chart",
            description=description,
            category=ToolCategory.VISUALIZATION,
            function_schema=function_schema,
            version="0.3.0",
            requires_context=True,
        )

    async def execute(
        self,
        context: Optional[Any] = None,
        chart_type: str = "",
        title: str = "",
        chart_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
        output_context: str = "word",
        style_profile: str = "report",
        notes: Optional[Any] = None,
        options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        opts = dict(options or {})
        if notes is not None:
            opts["notes"] = notes
        metadata = {
            "tool_name": self.name,
            "schema_version": "business_chart.v1",
            "chart_type": chart_type,
            "output_context": output_context or "word",
            "style_profile": style_profile or "report",
            "reference_paths": business_chart_reference_paths(),
        }
        if chart_type not in SPECIALIZED_CHART_TYPES:
            return self._failed_result(
                f"create_business_chart 不支持图型 {chart_type!r}；仅支持专用业务图型。"
                "常规问数交互图请使用 execute_echarts_python，静态分析和报告图请使用 execute_python。",
                metadata, chart_type, title, file_path,
            )
        if isinstance(data, dict) and "charts" in data:
            return self._failed_result(
                "不接收 charts 嵌套多图请求；专用业务图分别调用，自定义组合图使用 execute_python。",
                metadata, chart_type, title, file_path,
            )
        if data is None and not file_path:
            return self._failed_result(
                "必须提供 data 或 file_path 作为图表数据输入。",
                metadata,
                chart_type,
                title,
                file_path,
            )
        if opts.get("dry_run"):
            result = {
                "success": True,
                "status": "success",
                "metadata": metadata,
                "data": {
                    "chart_id": chart_id,
                    "chart_type": chart_type,
                    "title": title,
                    "render_mode": "dry_run",
                    "file_path": file_path,
                    "has_inline_data": data is not None,
                    "notes": notes,
                },
                "summary": "业务图表请求已按 create_business_chart 统一入口解析；dry_run 未生成图片。",
            }
            self._attach_resume_context(result, file_path=file_path)
            result["resources"] = file_products(
                [
                    visual.get("local_path") or visual.get("file_path")
                    for visual in result.get("visuals", [])
                    if isinstance(visual, dict)
                    and (visual.get("local_path") or visual.get("file_path"))
                ],
                tool_name=self.name,
            )
            return result

        try:
            chart_data = self._resolve_chart_data(data=data, file_path=file_path, context=context)

            from app.tools.visualization.create_business_chart.renderer import render_business_chart

            rendered = render_business_chart(
                chart_id=chart_id,
                chart_type=chart_type,
                title=title,
                data=chart_data,
                output_context=output_context or "word",
                style_profile=style_profile or "report",
                options=opts,
            )
            catalog_visuals = []
            for visual in rendered.get("visuals", []):
                if not isinstance(visual, dict):
                    continue
                catalog_visual = dict(visual)
                # Preview and download URLs are projected only after the
                # resource group is persisted; tool results keep server paths
                # private to the publication boundary.
                catalog_visual.pop("url", None)
                catalog_visual.pop("image_url", None)
                catalog_visual.pop("markdown_image", None)
                catalog_visuals.append(catalog_visual)
            rendered = {**rendered, "visuals": catalog_visuals}
            metadata.update(rendered.get("metadata", {}))
            if file_path:
                metadata["source_file_path"] = file_path
            result = {
                "success": True,
                "status": "success",
                "metadata": metadata,
                "data": rendered,
                "visuals": rendered.get("visuals", []),
                "summary": rendered.get("summary", "业务图表已生成。"),
            }
            self._attach_resume_context(result, file_path=file_path)
            result["resources"] = resources_for_visuals(
                result.get("visuals", []), tool_name=self.name
            )
            return result
        except ChartDataError as exc:
            return self._failed_result(str(exc), metadata, chart_type, title, file_path)
        except (KeyError, ValueError, TypeError) as exc:
            return self._failed_result(str(exc), metadata, chart_type, title, file_path)

    def _resolve_chart_data(
        self,
        data: Optional[Dict[str, Any]],
        file_path: Optional[str],
        context: Optional[Any],
    ) -> Dict[str, Any]:
        if data is not None:
            return data
        if not file_path:
            raise ChartDataError("必须提供 data 或 file_path 作为图表数据输入。")
        if context is None:
            raise ChartDataError("使用 file_path 调用 create_business_chart 需要 ExecutionContext。")

        try:
            payload_loader = getattr(context, "get_data_payload", None)
            loaded = (
                payload_loader(file_path)
                if callable(payload_loader)
                else context.get_raw_data(file_path)
            )
        except AttributeError as exc:
            raise ChartDataError("当前上下文无法读取 file_path。") from exc

        return self._normalize_loaded_chart_data(loaded, file_path)

    def _normalize_loaded_chart_data(self, loaded: Any, file_path: str) -> Dict[str, Any]:
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
            f"file_path {file_path} 未保存为 create_business_chart 可直接使用的图表数据对象；"
            "请先整理为对应业务图型文档要求的数据对象。"
        )

    def _failed_result(
        self,
        error: str,
        metadata: Dict[str, Any],
        chart_type: str,
        title: str,
        file_path: Optional[str],
    ) -> Dict[str, Any]:
        if file_path:
            metadata["source_file_path"] = file_path
        return {
            "success": False,
            "status": "failed",
            "error": error,
            "metadata": metadata,
            "data": {
                "chart_type": chart_type,
                "title": title,
                "file_path": file_path,
            },
            "visuals": [],
            "summary": f"业务图表生成失败：{error}",
        }

    def _attach_resume_context(
        self,
        result: Dict[str, Any],
        file_path: Optional[str],
    ) -> None:
        refs: Dict[str, Any] = {}
        if file_path:
            refs = merge_refs(
                refs,
                {"data": [build_data_file_ref(file_path, usage="source")]},
            )

        file_refs = []
        visual_refs = []
        generated_visuals = []
        for visual in result.get("visuals") or []:
            if not isinstance(visual, dict):
                continue
            local_path = visual.get("local_path")
            visual_file_path = visual.get("file_path")
            image_url = visual.get("image_url")
            visual_id = visual.get("id")
            visual_title = visual.get("title")
            tool_path = local_path or visual_file_path

            visual_ref = build_visual_ref(
                id=visual_id,
                type=visual.get("type") or "image",
                title=visual_title,
                image_url=image_url,
                local_path=local_path,
                file_path=visual_file_path,
                chart_type=result.get("metadata", {}).get("chart_type"),
            )
            if visual_ref:
                visual_refs.append(visual_ref)

            if tool_path:
                path = Path(tool_path)
                file_refs.append(
                    build_file_ref(
                        path,
                        type="image",
                        format=path.suffix.lstrip(".") or None,
                        size=path.stat().st_size if path.exists() else None,
                        usage="business_chart",
                        preferred_for=["read_file", "list_session_resources"],
                        visual_id=visual_id,
                    )
                )
                generated_visuals.append(
                    {
                        "id": visual_id,
                        "title": visual_title,
                        "tool_path": str(path),
                        "image_url": image_url,
                    }
                )

        refs = merge_refs(
            refs,
            {"files": file_refs} if file_refs else None,
            {"visuals": visual_refs} if visual_refs else None,
        )
        if refs:
            result["refs"] = refs

        llm_resume: Dict[str, Any] = {}
        if file_path:
            llm_resume["source_file_path"] = file_path
        if generated_visuals:
            llm_resume["generated_visuals"] = generated_visuals
            first_path = generated_visuals[0].get("tool_path")
            if first_path:
                llm_resume["tool_hint"] = (
                    f"Use read_file(path='{first_path}', as_multimodal_attachment=true) "
                    "to inspect this image internally. Do not place this server "
                    "path in the final answer or Markdown image URL; the chart is "
                    "published through session resources."
                )
        if llm_resume:
            result["llm_resume"] = llm_resume
