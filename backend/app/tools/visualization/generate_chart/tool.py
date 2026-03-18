"""
智能图表生成工具（v3.0 - 统一格式）

完全使用v3.0标准格式：
- 后端生成统一的ChartResponse格式
- 前端接收标准化的图表数据
- 删除所有兼容代码
"""
import json
from typing import Dict, Any, List, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.visualization.generate_chart.chart_templates import (
    get_chart_template_registry,
    ChartTemplate
)
from app.schemas.visualization import ChartResponse

logger = structlog.get_logger()


class GenerateChartTool(LLMTool):
    """
    智能图表生成工具 - 原始数据即时可视化（v3.1扩展版）

    核心职责：
    1. 对原始/临时数据进行灵活可视化
    2. 支持15种图表类型（基础、气象、空间、3D）
    3. 使用模板库或LLM智能生成
    4. 支持多图表组合输出

    与 smart_chart_generator 的区别：
    ┌──────────────────────────────────────────────────────────────┐
    │ generate_chart                 vs  smart_chart_generator     │
    ├──────────────────────────────────────────────────────────────┤
    │ 原始/临时数据（dict/list）           已存储数据（data_id）   │
    │ 高自由度、灵活性强                   固定格式、严格验证      │
    │ 可一次生成多图                       单图输出                │
    │ 适合探索性分析                       适合标准化分析          │
    │ 15种图表类型全支持                   15种图表类型全支持      │
    │ LLM智能生成 + 模板库                 转换器驱动              │
    │ 无数据溯源                           完整数据溯源            │
    └──────────────────────────────────────────────────────────────┘

    使用场景：
    1. 原始数据快速可视化：generate_chart(data=[...], scenario="custom", chart_type_hint="pie")
    2. 气象数据分析：generate_chart(data=[{"wind_speed": ..., ...}], chart_type_hint="wind_rose")
    3. 空间数据可视化：generate_chart(data=[{"lng": ..., "lat": ..., ...}], chart_type_hint="map")
    4. 多图组合生成：generate_chart(data={...}, scenario="vocs_analysis")  # 自动生成饼图+时序图
    5. 探索性分析：数据格式未知，使用chart_type_hint="auto"让LLM智能推荐

    不适用场景：
    - 已存储的PMF结果 → 使用 smart_chart_generator(data_id="pmf_result:...")
    - 需要数据溯源追踪 → 使用 smart_chart_generator
    - 固定格式分析结果 → 使用 smart_chart_generator

    决策规则：
    - 如果有data_id（数据已存储） → 使用 smart_chart_generator
    - 如果是PMF/OBM分析结果 → 使用 smart_chart_generator
    - 如果是原始数据快速可视化 → 使用 generate_chart
    - 如果需要多图组合 → 使用 generate_chart
    """

    def __init__(self):
        function_schema = {
            "name": "generate_chart",
            "description": """
根据原始数据生成v3.1标准格式的图表配置（支持15种类型）。

【核心特点】
- 参数简单：只需传入数据 + 指定图表类型
- 智能回退：模板优先，失败时自动回退到LLM生成
- 格式统一：输出UDF v2.0格式（含visuals字段）

【重要：标准字段名称】
生成图表时必须使用以下标准字段名称：
【污染物字段】PM2_5, PM10, O3, NO2, SO2, CO（注意：O3不是o3，PM2_5不是PM2.5）
【气象字段】temperature_2m, wind_speed_10m, wind_direction_10m, relative_humidity_2m, surface_pressure
【时间字段】timestamp
【地理字段】station_name, city, lat, lon

【使用方式】
1. 传入实际数据对象（list/dict格式）
2. 明确指定图表类型（从15种类型中选择）
3. 工具自动尝试模板生成，失败时回退到LLM生成

【示例】
- generate_chart(data=[{"name": "A", "value": 10}], chart_type="pie")
- generate_chart(data={"x": ["1月", "2月"], "y": [100, 120]}, chart_type="bar")
- generate_chart(data=[{"timestamp": "2025-01", "O3": 76, "PM2_5": 10}], chart_type="timeseries")

【与smart_chart_generator的区别】
┌──────────────────────────────────────────────────────────────┐
│ generate_chart                   smart_chart_generator      │
├──────────────────────────────────────────────────────────────┤
│ 处理原始/临时数据（list/dict）    处理已存储数据（data_id）   │
│ 简单参数：data + chart_type        复杂参数：data_id + 验证  │
│ 适合快速可视化                    适合标准分析              │
│ 模板+LLM双层生成                  模板驱动                  │
│ 无数据溯源                        完整数据溯源              │
└──────────────────────────────────────────────────────────────┘

【决策规则】
- 如果数据已存储到统一存储（通过data_id引用）→ 使用smart_chart_generator
- 如果是原始数据需要快速可视化 → 使用generate_chart
- 如果是PMF/OBM分析结果 → 使用smart_chart_generator
- 如果不确定，优先使用generate_chart（更简单）

【支持的15种图表类型】

基础图表（适用于常规数据分析）：
- pie: 饼图（占比/组成关系）- 数据格式：[{"name": "类别", "value": 数值}]
- bar: 柱状图（对比不同类别）- 数据格式：{"x": [类别], "y": [数值]}
- line: 折线图（单一指标趋势）- 数据格式：{"x": [时间], "y": [数值]}
- timeseries: 时序图（多系列对比）- 数据格式：{"x": [时间], "series": [{"name": "系列", "data": [...]}]}
- radar: 雷达图（多维度对比）- 数据格式：{"dimensions": [维度], "series": [{"name": "系列", "values": [...]}]}

气象专业图表（适用于气象数据）：
- wind_rose: 风向玫瑰图（需要wind_speed+wind_direction字段）
- profile: 边界层廓线图（需要altitude/height字段）

空间图表（适用于地理数据）：
- map: 地图（需要longitude+latitude字段）
- heatmap: 热力图（需要longitude+latitude+value字段）

3D图表（适用于三维空间数据）：
- scatter3d: 3D散点图（需要x+y+z字段）
- surface3d: 3D曲面图（需要x+y+z字段）
- line3d: 3D线图（需要x+y+z字段）
- bar3d: 3D柱状图（需要x+y+z字段）
- volume3d: 3D体素图（需要x+y+z+values字段）

【选择建议】
- 数据包含name+value字段 → pie
- 数据包含category/value或x/y字段 → bar/line
- 数据包含时间序列 → timeseries
- 数据包含wind_speed+wind_direction → wind_rose
- 数据包含longitude+latitude → map或heatmap
- 数据包含x+y+z三个坐标 → 3D图表

【注意事项】
- data参数必须是实际的数据对象，不能是字符串或data_id
- chart_type必须明确指定（不支持"auto"）
- 如果数据已存储，请使用smart_chart_generator工具
- 工具会自动处理模板和LLM回退，无需手动选择

返回格式：UDF v2.0标准格式（含visuals字段）
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "description": "要可视化的数据。必须是实际的数据对象（list/dict），\n不能传入data_id字符串、字符串描述或占位符。\n如果数据已存储到统一存储并有data_id，请使用smart_chart_generator工具。"
                    },
                    "chart_type": {
                        "type": "string",
                        "description": """
图表类型(必须明确指定)。支持15种类型:

基础图表(适用于常规数据分析):
- pie: 饼图(占比/组成关系) - 数据格式: [{"name": "类别", "value": 数值}]
- bar: 柱状图(对比不同类别) - 数据格式: {"x": [类别], "y": [数值]}
- line: 折线图(单一指标趋势) - 数据格式: {"x": [时间], "y": [数值]}
- timeseries: 时序图(多系列对比) - 数据格式: {"x": [时间], "series": [{"name": "系列", "data": [...]}]}
- radar: 雷达图(多维度对比) - 数据格式: {"dimensions": [维度], "series": [{"name": "系列", "values": [...]}]}

气象专业图表(适用于气象数据):
- wind_rose: 风向玫瑰图(需要wind_speed+wind_direction字段)
- profile: 边界层廓线图(需要altitude/height字段)

空间图表(适用于地理数据):
- map: 地图(需要longitude+latitude字段)
- heatmap: 热力图(需要longitude+latitude+value字段)

3D图表(适用于三维空间数据):
- scatter3d: 3D散点图(需要x+y+z字段)
- surface3d: 3D曲面图(需要x+y+z字段)
- line3d: 3D线图(需要x+y+z字段)
- bar3d: 3D柱状图(需要x+y+z字段)
- volume3d: 3D体素图(需要x+y+z+values字段)

选择建议:
- 数据包含name+value字段 → pie
- 数据包含category/value或x/y字段 → bar/line
- 数据包含时间序列 → timeseries
- 数据包含wind_speed+wind_direction → wind_rose
- 数据包含longitude+latitude → map或heatmap
- 数据包含x+y+z三个坐标 → 3D图表
                        """.strip(),
                        "enum": [
                            # 基础图表
                            "pie", "bar", "line", "timeseries", "radar",
                            # 气象图表
                            "wind_rose", "profile",
                            # 空间图表
                            "map", "heatmap",
                            # 3D图表
                            "scatter3d", "surface3d", "line3d", "bar3d", "volume3d"
                        ]
                    },
                    "title": {
                        "type": "string",
                        "description": "图表标题(可选)"
                    },
                    "pollutant": {
                        "type": "string",
                        "description": "污染物类型(可选)"
                    },
                    "station_name": {
                        "type": "string",
                        "description": "站点名称(可选)"
                    },
                    "venue_name": {
                        "type": "string",
                        "description": "场地名称(可选)"
                    },
                    "meta": {
                        "type": "object",
                        "description": "额外元数据(可选),可包含pollutant、station_name、venue_name等信息"
                    }
                },
                "required": ["data", "chart_type"]
            }
        }

        super().__init__(
            name="generate_chart",
            description="Generate v3.0 standardized chart configurations (Context-Aware V2)",
            category=ToolCategory.VISUALIZATION,
            function_schema=function_schema,
            version="3.1.0",
            requires_context=True
        )

        self.template_registry = get_chart_template_registry()

    async def execute(
        self,
        context: Any,
        data: Dict[str, Any],
        chart_type: str,
        title: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行图表生成（简化版 - v3.1格式）

        简化逻辑：
        1. 直接使用传入的数据（不处理data_id引用）
        2. 根据chart_type直接尝试模板生成
        3. 模板失败时回退到LLM生成
        4. 返回UDF v2.0格式结果

        参数:
            context: 执行上下文
            data: 实际数据对象(list/dict)，直接传入，不通过data_id
            chart_type: 图表类型(15种枚举值之一)
            title: 图表标题(可选)
            meta: 额外元数据(可选,可包含pollutant、station_name等)

        返回:
            UDF v2.0格式结果(含visuals字段)
        """
        try:
            # Step 1: 验证输入参数
            if not data:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "generate_chart",
                        "error_type": "empty_data"
                    },
                    "summary": "[FAIL] 数据不能为空"
                }

            # 标准化chart_type：处理常见别名和拼写变体
            chart_type_aliases = {
                "time_series": "timeseries",
                "time-series": "timeseries",
                "timeseries": "timeseries",
                "pie": "pie",
                "bar": "bar",
                "line": "line",
                "radar": "radar",
                "wind_rose": "wind_rose",
                "windrose": "wind_rose",
                "wind-rose": "wind_rose",
                "profile": "profile",
                "map": "map",
                "heatmap": "heatmap",
                "heat-map": "heatmap",
                "scatter3d": "scatter3d",
                "scatter-3d": "scatter3d",
                "scatter_3d": "scatter3d",
                "surface3d": "surface3d",
                "surface-3d": "surface3d",
                "surface_3d": "surface3d",
                "line3d": "line3d",
                "line-3d": "line3d",
                "line_3d": "line3d",
                "bar3d": "bar3d",
                "bar-3d": "bar3d",
                "bar_3d": "bar3d",
                "volume3d": "volume3d",
                "volume-3d": "volume3d",
                "volume_3d": "volume3d",
            }

            # 应用别名映射
            original_chart_type = chart_type
            chart_type = chart_type_aliases.get(chart_type.lower(), chart_type)

            # 验证标准化后的chart_type是否为支持的类型
            supported_types = [
                "pie", "bar", "line", "timeseries", "radar",
                "wind_rose", "profile", "map", "heatmap",
                "scatter3d", "surface3d", "line3d", "bar3d", "volume3d"
            ]
            if chart_type not in supported_types:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "generate_chart",
                        "error_type": "invalid_chart_type",
                        "original_input": original_chart_type,
                        "chart_type": chart_type,
                        "supported_types": supported_types
                    },
                    "summary": f"[FAIL] 不支持的图表类型: '{original_chart_type}' (标准化后: '{chart_type}')。支持的类型: {', '.join(supported_types)}"
                }

            # 记录类型映射（如果有）
            if original_chart_type != chart_type:
                logger.info(
                    "chart_type_normalized",
                    original=original_chart_type,
                    normalized=chart_type
                )

            # 准备元数据
            chart_meta = meta or {}

            # Step 2: 尝试使用模板生成
            chart_response = None
            method = None
            template_used = None

            logger.info(
                "attempting_template_generation",
                chart_type=chart_type
            )

            try:
                # 准备模板参数
                template_kwargs = {
                    "title": title,
                    "meta": chart_meta
                }

                # 预处理数据（简化版）
                processed_data = self._preprocess_data_for_simple_template(chart_type, data)

                # 生成图表
                chart_dict = self.template_registry.generate(
                    template_id=chart_type,
                    data=processed_data,
                    **template_kwargs
                )

                if chart_dict and isinstance(chart_dict, dict):
                    # 验证模板输出有效性
                    if self._is_valid_chart_output(chart_dict):
                        # v3.1增强
                        from app.utils.chart_data_converter import _validate_and_enhance_chart_v3_1

                        enhanced_chart = _validate_and_enhance_chart_v3_1(
                            chart=chart_dict,
                            generator=f"template:{chart_type}",
                            original_data_ids=None,
                            scenario="custom"
                        )

                        if "error" in enhanced_chart:
                            logger.warning(
                                "chart_v3_1_enhancement_failed",
                                error=enhanced_chart.get("error"),
                                chart_id=chart_dict.get("id")
                            )
                            chart_response = chart_dict
                        else:
                            chart_response = enhanced_chart

                        method = "template"
                        template_used = chart_type

                        logger.info(
                            "template_generation_success",
                            chart_type=chart_type,
                            chart_id=chart_response.get("id")
                        )
                    else:
                        logger.warning(
                            "template_output_invalid",
                            chart_type=chart_type,
                            reason="模板生成了无效数据（空数据或占位符）"
                        )

            except Exception as exc:
                logger.warning(
                    "template_generation_failed",
                    chart_type=chart_type,
                    error=str(exc)
                )
                # 模板失败，继续到LLM生成
                pass

            # Step 3: LLM智能生成（增强版 - 支持完整ECharts配置）
            if not chart_response:
                logger.info(
                    "falling_back_to_llm_generation",
                    chart_type=chart_type
                )

                # 【新增】增强版LLM生成 - 支持完整ECharts配置
                chart_response = await self._generate_full_echarts_config(
                    data=data,
                    chart_type=chart_type,
                    title=title,
                    meta=chart_meta
                )

                if chart_response:
                    method = "llm_enhanced"
                    logger.info(
                        "llm_enhanced_generation_success",
                        chart_type=chart_type,
                        chart_id=chart_response.get("id")
                    )
                else:
                    # 回退到原始LLM生成
                    chart_response = await self._generate_with_llm_v3(
                        data=data,
                        chart_type_hint=chart_type,
                        title=title,
                        x_field=None,
                        y_field=None,
                        meta=chart_meta
                    )
                    method = "llm_generated"

                    logger.info(
                        "llm_generation_success",
                        chart_type=chart_type,
                        chart_id=chart_response.get("id")
                    )

            # Step 4: v3.1增强（确保统一格式）
            if chart_response:
                from app.utils.chart_data_converter import _validate_and_enhance_chart_v3_1

                enhanced_chart = _validate_and_enhance_chart_v3_1(
                    chart=chart_response,
                    generator=method,
                    original_data_ids=None,
                    scenario="custom"
                )

                if "error" not in enhanced_chart:
                    chart_response = enhanced_chart
                    logger.info(
                        "chart_enhanced_to_v3_1",
                        chart_id=chart_response.get("id"),
                        method=method
                    )

            # Step 5: 存储配置
            data_id = None
            try:
                from datetime import datetime
                import uuid
                from app.schemas.chart import ChartConfig

                # 创建ChartConfig模型
                chart_config_model = ChartConfig(
                    chart_id=chart_response.get("id", "chart_" + uuid.uuid4().hex[:8]),
                    chart_type=chart_response.get("type", chart_type),
                    title=chart_response.get("title", title or "图表"),
                    payload=chart_response,
                    method=method,
                    template_used=template_used,
                    scenario="custom",
                    data_record_count=len(data) if isinstance(data, list) else 1,
                    pollutant=chart_meta.get("pollutant"),
                    station_name=chart_meta.get("station_name"),
                    venue_name=chart_meta.get("venue_name"),
                    generated_at=datetime.now().isoformat(),
                    metadata={
                        **chart_meta,
                        "format_version": "3.1",
                        "simplified": True  # 标记为简化版本
                    }
                )

                # 保存到context
                # save_data() 返回 {"data_id": str, "file_path": str}
                data_ref = context.save_data(
                    data=[chart_config_model],
                    schema="chart_config",
                    metadata={
                        "chart_type": chart_config_model.chart_type,
                        "method": method,
                        "template_used": template_used,
                        "scenario": "custom",
                        "format_version": "3.1",
                        "simplified": True
                    }
                )
                data_id = data_ref["data_id"]
                file_path = data_ref["file_path"]

                logger.info("chart_config_saved", data_id=data_id, file_path=file_path)

            except Exception as exc:
                logger.error(
                    "chart_config_save_failed",
                    error=str(exc),
                    exc_info=True
                )
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "generate_chart",
                        "error_type": "data_save_failed",
                        "method": method
                    },
                    "summary": f"[FAIL] 图表配置保存失败: {str(exc)}"
                }

            # Step 6: 返回UDF v2.0格式结果
            # 确保chart_response是纯字典
            chart_dict = chart_response
            if hasattr(chart_dict, 'model_dump'):
                chart_dict = chart_dict.model_dump()
            elif hasattr(chart_dict, 'dict'):
                chart_dict = chart_dict.dict()

            # 【新增】分析数据有效性（用于LLM观测）
            data_analysis = self._analyze_chart_data_validity(chart_dict, data)

            # 构建VisualBlock
            from app.schemas.unified import VisualBlock

            visual_block = VisualBlock(
                id=chart_dict.get("id", f"chart_{data_id}"),
                type="chart",
                schema="chart_config",
                payload=chart_dict,
                meta={
                    "source_data_ids": [data_id] if data_id else [],
                    "schema_version": "v2.0",
                    "generator": "generate_chart",
                    "scenario": "custom",
                    "method": method,
                    "template_used": template_used,
                    "layout_hint": "main",
                    # 【新增】详细的生成过程信息
                    "generation_details": {
                        "attempted_method": method,
                        "template_used": template_used,
                        "data_valid": data_analysis["is_valid"],
                        "data_issue": data_analysis.get("issue", "none"),
                        "data_point_count": data_analysis.get("data_point_count", 0),
                        "null_count": data_analysis.get("null_count", 0),
                        "chart_type_confirmed": chart_dict.get("type"),
                        "data_structure": data_analysis.get("structure", "unknown"),
                        "recommendation": data_analysis.get("recommendation", "")
                    }
                }
            )

            logger.info(
                "generate_chart_success",
                chart_type=chart_dict.get("type"),
                method=method,
                data_id=data_id,
                data_valid=data_analysis["is_valid"]
            )

            # 返回UDF v2.0格式
            return {
                "status": "success",
                "success": True,
                "data": None,  # v2.0格式使用visuals字段
                "visuals": [visual_block.dict()],
                "metadata": {
                    "tool_name": "generate_chart",
                    "data_id": data_id,
                    "chart_type": chart_dict.get("type"),
                    "method": method,
                    "template_used": template_used,
                    "scenario": "custom",
                    "schema_version": "v2.0",
                    "source_data_ids": [data_id] if data_id else [],
                    "generator": "generate_chart",
                    "registry_schema": "chart_config",
                    # 【新增】详细的生成过程和数据分析
                    "generation_debug": {
                        "method_used": method,  # template/llm_generated/fallback
                        "template_id": template_used,
                        "data_analysis": data_analysis,  # 数据有效性分析
                        "raw_data_size": len(data) if isinstance(data, list) else 1,
                        "chart_data_size": len(chart_dict.get("data", [])),
                        "generation_successful": True,
                        "timestamp": __import__('datetime').datetime.now().isoformat()
                    }
                },
                "data_id": data_id,
                "file_path": file_path,
                "summary": f"✅ 图表生成完成，类型: {chart_dict.get('type')}，方式: {method}，数据有效性: {'有效' if data_analysis['is_valid'] else '异常'} (UDF v2.0)"
            }

        except Exception as e:
            logger.error(
                "generate_chart_failed",
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "tool_name": "generate_chart",
                    "error_type": "execution_failed",
                    "error": str(e)
                },
                "summary": f"[FAIL] 图表生成失败: {str(e)[:100]}"
            }

    async def _generate_with_llm_v3(
        self,
        data: Dict[str, Any],
        chart_type_hint: str,
        title: Optional[str],
        x_field: Optional[str],
        y_field: Optional[str],
        meta: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        使用LLM生成v3.1格式图表（支持15种类型）

        优先使用 prompt_registry 中的专用prompt，回退到通用prompt
        """
        from app.services.llm_service import llm_service
        from app.prompts.chart_generation import get_prompt_registry

        # 准备数据样本（用于日志记录）
        data_sample = json.dumps(data, ensure_ascii=False, indent=2)[:4000]

        # 尝试使用专用prompt
        prompt_registry = get_prompt_registry()
        prompt_template = prompt_registry.get_prompt(chart_type_hint)

        if prompt_template and chart_type_hint != "auto":
            # 使用专用prompt模板
            prompt = prompt_template.build_prompt(data, title)
            logger.info(
                "using_specialized_prompt",
                chart_type=chart_type_hint,
                prompt_class=prompt_template.__class__.__name__
            )
        else:
            # 回退到通用prompt
            logger.info(
                "using_generic_prompt",
                chart_type=chart_type_hint,
                reason="no_specialized_prompt_available" if chart_type_hint != "auto" else "auto_mode"
            )

            # 构建通用提示词（v3.1格式，支持15种类型）
            # 获取字段映射信息以帮助LLM理解数据
            from app.utils.data_standardizer import get_data_standardizer
            standardizer = get_data_standardizer()
            field_mapping_info = standardizer.get_field_mapping_info()

            # 提供常见污染物字段映射示例
            common_pollutant_mappings = [
                ("PM2_5", "PM2.5", "PM25", "pm2_5"),
                ("O3", "o3", "O3_8h"),
                ("NO2", "no2", "NO2"),
                ("PM10", "pm10"),
                ("SO2", "so2"),
                ("CO", "co")
            ]
            pollutant_mapping_examples = []
            for variants in common_pollutant_mappings:
                pollutant_mapping_examples.append("/".join(variants))
            pollutant_mapping_str = ", ".join(pollutant_mapping_examples[:5])

            prompt = f"""
你是一个高级数据可视化专家。请分析数据并生成v3.1标准格式的图表配置。

# 数据样本（前4000字符）
```json
{data_sample}
```

# 需求
- 图表类型提示: {chart_type_hint}
- 标题: {title or '自动生成'}
- X轴字段: {x_field or '自动识别'}
- Y轴字段: {y_field or '自动识别'}

# 【重要】标准字段名称规范
生成图表时必须使用以下标准字段名称（从data_sample中提取实际字段名，然后映射到标准名称）：

【时间字段】
- timestamp: 时间戳（标准格式：YYYY-MM-DD HH:MM:SS）

【地理字段】
- station_name: 站点名称
- city: 城市名称
- lat: 纬度
- lon: 经度

【污染物字段（标准名称）】
- PM2_5: PM2.5（注意：使用下划线，不是点号）
- PM10: PM10
- O3: 臭氧（注意：使用大写O，不是小写o）
- O3_8h: 8小时臭氧平均值（与O3是不同的指标！）
- NO2: 二氧化氮
- SO2: 二氧化硫
- CO: 一氧化碳

【气象字段】
- temperature_2m: 2米温度
- wind_speed_10m: 10米风速
- wind_direction_10m: 10米风向
- relative_humidity_2m: 2米相对湿度
- surface_pressure: 地面气压

【数据筛选要求】
1. **严格使用标准字段名**：O3不是o3，PM2_5不是PM2.5或PM25
2. **从data_sample提取**：必须检查data_sample中的实际字段名
3. **字段名匹配**：生成的图表中字段名必须与实际数据字段名完全一致
4. **大小写敏感**：严格区分大小写（O3≠o3，PM2_5≠PM2.5）

【错误示例】
❌ 错误：使用"o3"（应为"O3"）
❌ 错误：使用"PM2.5"（应为"PM2_5"）
❌ 错误：使用"PM25"（应为"PM2_5"）
✅ 正确：从data_sample中提取真实字段名，映射到上述标准名称

# 支持的图表类型（15种）

## 基础图表（适用于常规数据分析）

### pie（饼图）
- 适用场景: 展示占比/组成关系
- 最佳实践: 污染源贡献率、物种占比、组分分布
- 数据格式: [{{name: "类别", value: 数值}}, ...]
- 字段要求: name为类别名，value为数值（如PM2_5或O3的浓度值）

### bar（柱状图）
- 适用场景: 对比不同类别的数值
- 最佳实践: 不同站点对比、不同污染物对比
- 数据格式: {{"x": [类别1, 类别2, ...], "y": [数值1, 数值2, ...]}}
- 字段要求: x为类别列表（如站点名、时间等），y为对应的数值列表

### line（折线图）
- 适用场景: 展示单一指标的趋势变化
- 最佳实践: 单一污染物随时间变化（如O3浓度日变化）
- 数据格式: {{"x": [时间1, 时间2, ...], "y": [数值1, 数值2, ...]}}
- 字段要求: x为时间序列，y为对应时间的污染物浓度值（必须使用标准字段名：PM2_5, O3, NO2等）

### timeseries（时序图）
- 适用场景: 展示多系列时间序列，支持多条线对比
- 最佳实践: 多污染物时序对比、多站点时序对比
- 数据格式: {{"x": [时间1, 时间2, ...], "series": [{{name: "系列1", data: [...]}}, ...]}}
- 字段要求: series中name必须使用标准字段名（O3, PM2_5, PM10等），data为对应时间序列的数值

### radar（雷达图）
- 适用场景: 多维度对比
- 最佳实践: 敏感性分析、多指标综合评价
- 数据格式: {{"dimensions": [维度1, 维度2, ...], "series": [{{name: "系列1", values: [...]}}]}}
- 字段要求: dimensions为评估维度，series中name为指标名称（如"敏感性"）

---

## 气象专业图表（适用于气象数据）

### wind_rose（风向玫瑰图）
- 适用场景: 展示风向风速分布
- 触发条件: **必须包含wind_speed和wind_direction字段**
- 数据格式: {{"sectors": [{{direction: "N", angle: 0, avg_speed: 3.5, max_speed: 8.2, count: 120, speed_distribution: {{"0-2": 30, "2-5": 60}}}}]}}

### profile（边界层廓线图）
- 适用场景: 展示大气垂直结构（高度-参数关系）
- 触发条件: **必须包含altitude或height字段**
- 数据格式: {{"altitudes": [0, 100, 200, ...], "elements": [{{name: "温度", unit: "°C", data: [25.0, 24.5, ...]}}]}}

---

## 空间图表（适用于地理数据）

### map（地图）
- 适用场景: 展示地理分布、站点位置
- 触发条件: **必须包含longitude和latitude字段**
- 数据格式: {{"map_center": {{lng: 114.05, lat: 22.54}}, "zoom": 12, "layers": [{{type: "marker", data: [{{lng: 114.05, lat: 22.54, name: "站点A", value: 35}}]}}]}}

### heatmap（热力图）
- 适用场景: 展示空间密度/强度分布
- 触发条件: **必须包含longitude、latitude和value字段**
- 数据格式: {{"points": [{{lng: 114.05, lat: 22.54, value: 45.2}}, ...]}}

---

## 3D图表（适用于三维空间数据）

### scatter3d（3D散点图）
- 适用场景: 展示3维空间分布
- 触发条件: **必须包含x、y、z三个坐标字段**
- 数据格式: {{"x": [...], "y": [...], "z": [...]}}

### surface3d（3D曲面图）
- 适用场景: 展示3维连续曲面
- 数据格式: {{"x": [...], "y": [...], "z": [[...]]}}  # z是二维数组

### line3d（3D线图）
- 适用场景: 展示3维轨迹
- 数据格式: {{"x": [...], "y": [...], "z": [...]}}

### bar3d（3D柱状图）
- 适用场景: 3维柱状对比
- 数据格式: {{"x": [...], "y": [...], "z": [...]}}

### volume3d（3D体素图）
- 适用场景: 展示3维体积数据
- 数据格式: {{"x": [...], "y": [...], "z": [...], "values": [[[]]]}}  # values是三维数组

---

# v3.1输出格式（必须严格遵循）

返回JSON格式（不要markdown代码块）：
{{
    "id": "unique_chart_id",
    "type": "选择上述15种之一",
    "title": "图表标题",
    "data": {{
        // 根据type选择对应的数据结构（见上述各类型说明）
        // ⚠️ 重要：data中使用的字段名必须与实际数据中的字段名完全一致！
    }},
    "meta": {{
        "schema_version": "3.1",
        "unit": "单位",
        "station_name": "站点名",
        "pollutant": "污染物类型",
        "generator": "llm_generated",
        "scenario": "custom",
        "data_source": "generate_chart_llm",
        "record_count": 数据记录数
    }}
}}

【必读】输出前自检清单（LLM必须执行）：
☐ 1. 检查data_sample中的实际字段名
☐ 2. 确认生成的图表中使用的字段名与实际数据字段名完全一致
☐ 3. 验证污染物字段使用标准名称（PM2_5不是PM2.5或PM25，O3不是o3）
☐ 4. 确保chart_type匹配data的数据结构
☐ 5. 验证所有数值类型正确（无字符串数字）

# 智能决策规则（优先级从高到低）

1. **数据包含wind_speed+wind_direction** → 优先推荐 wind_rose
2. **数据包含altitude或height** → 优先推荐 profile
3. **数据包含longitude+latitude+value** → 优先推荐 heatmap
4. **数据包含longitude+latitude** → 优先推荐 map
5. **数据包含x+y+z（三个坐标）** → 优先推荐 3D 图表（scatter3d/line3d等）
6. **数据包含时间序列+多个污染物/指标** → 推荐 timeseries
7. **数据包含时间序列+单一指标** → 推荐 line 或 timeseries
8. **数据只有单一时间点** → 推荐 bar
9. **数据是占比/组成关系** → 推荐 pie
10. **数据是对比分析** → 推荐 bar
11. **数据是多维度评价** → 推荐 radar

# 重要规则

1. **必须使用data字段**（不是payload或option）
2. **确保所有数值类型正确**（浮点数、整数）
3. **meta.schema_version必须是"3.1"**
4. **type必须是上述15种之一**（不能自己发明类型）
5. **只返回JSON**（不要markdown代码块，不要额外文字）
6. **如果chart_type_hint不是auto**，优先使用提示的类型
7. **⚠️ 字段名必须匹配**：生成图表时使用的字段名必须与实际数据中的字段名完全一致！

# 数据分析提示

1. 观察数据结构：列表 vs 字典，嵌套层级
2. 检查字段名：是否包含特殊字段（wind_speed, longitude, altitude等）
3. 识别数据维度：一维（列表）、二维（时间序列）、三维（空间）
4. 判断数据关系：占比、趋势、对比、分布

请直接返回JSON（不要代码块标记）。
        """.strip()

        try:
            response = await llm_service.call_llm_with_json_response(prompt)

            # 验证v3.1格式
            if "id" not in response or "type" not in response or "data" not in response:
                raise ValueError("LLM返回的数据不是有效的v3.1格式")

            # 验证type是否在15种支持的类型中
            supported_types = [
                "pie", "bar", "line", "timeseries", "radar",
                "wind_rose", "profile",
                "map", "heatmap",
                "scatter3d", "surface3d", "line3d", "bar3d", "volume3d"
            ]

            chart_type = response.get("type")
            if chart_type not in supported_types:
                logger.warning(
                    "llm_chart_type_not_supported",
                    chart_type=chart_type,
                    supported_types=supported_types,
                    falling_back_to=chart_type_hint
                )
                # 回退到提示类型
                if chart_type_hint != "auto" and chart_type_hint in supported_types:
                    response["type"] = chart_type_hint
                else:
                    # 使用最保险的类型
                    response["type"] = "bar"

                logger.info(
                    "llm_chart_type_corrected",
                    original=chart_type,
                    corrected=response["type"]
                )

            # 确保meta中包含schema_version
            if "meta" not in response:
                response["meta"] = {}
            response["meta"]["schema_version"] = "3.1"
            response["meta"]["generator"] = "llm_generated"

            logger.info(
                "llm_chart_generated_v3_1",
                chart_type=response.get("type"),
                chart_id=response.get("id"),
                schema_version=response.get("meta", {}).get("schema_version", "unknown"),
                data_sample_size=len(data_sample)
            )

            return response

        except Exception as e:
            logger.error(
                "llm_generation_failed",
                error=str(e),
                chart_type_hint=chart_type_hint,
                exc_info=True
            )
            # 返回备用图表
            return self._create_fallback_chart_v3(data, chart_type_hint, title, meta)

    def _create_fallback_chart_v3(
        self,
        data: Any,
        chart_type_hint: str,
        title: Optional[str],
        meta: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        创建v3.1格式的备用图表（增强版 - 支持专业图表回退）

        优先级：
        1. 专业字段检测（wind_speed/longitude/xyz） → 专业图表
        2. 基础数据格式（name/value, category/value） → 基础图表
        3. 默认柱状图兜底
        """
        import time
        import random
        import uuid

        chart_id = f"fallback_{int(time.time())}_{random.randint(1000, 9999)}"
        chart_meta = meta or {}
        chart_meta["fallback"] = True
        chart_meta["schema_version"] = "3.1"

        # ============================================
        # 新增：专业图表字段检测（v3.1增强）
        # ============================================

        # 1. 风向玫瑰图回退（wind_rose）
        if self._check_data_has_fields(data, ["wind_speed", "wind_direction"]):
            logger.info(
                "fallback_to_wind_rose",
                reason="检测到wind_speed和wind_direction字段"
            )

            # 构建简化的风向玫瑰图（8方位）
            if isinstance(data, list) and data:
                try:
                    # 简单统计每个方向的平均风速
                    direction_stats = {
                        "N": [], "NE": [], "E": [], "SE": [],
                        "S": [], "SW": [], "W": [], "NW": []
                    }

                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        direction = item.get("wind_direction")
                        speed = item.get("wind_speed")
                        if direction is None or speed is None:
                            continue

                        try:
                            direction = float(direction)
                            speed = float(speed)
                        except (ValueError, TypeError):
                            continue

                        # 简单方向分组
                        if 337.5 <= direction or direction < 22.5:
                            direction_stats["N"].append(speed)
                        elif 22.5 <= direction < 67.5:
                            direction_stats["NE"].append(speed)
                        elif 67.5 <= direction < 112.5:
                            direction_stats["E"].append(speed)
                        elif 112.5 <= direction < 157.5:
                            direction_stats["SE"].append(speed)
                        elif 157.5 <= direction < 202.5:
                            direction_stats["S"].append(speed)
                        elif 202.5 <= direction < 247.5:
                            direction_stats["SW"].append(speed)
                        elif 247.5 <= direction < 292.5:
                            direction_stats["W"].append(speed)
                        elif 292.5 <= direction < 337.5:
                            direction_stats["NW"].append(speed)

                    # 构建sectors
                    sectors = []
                    total_count = sum(len(speeds) for speeds in direction_stats.values())

                    for dir_key in ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]:
                        speeds = direction_stats[dir_key]
                        sectors.append({
                            "direction": dir_key,
                            "angle": {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}[dir_key],
                            "avg_speed": round(sum(speeds) / len(speeds), 2) if speeds else 0,
                            "max_speed": round(max(speeds), 2) if speeds else 0,
                            "count": len(speeds),
                            "frequency": round(len(speeds) / total_count, 3) if total_count > 0 else 0,
                            "speed_distribution": {"0-2": 0, "2-5": 0, "5-10": 0, "10+": 0}
                        })

                    return {
                        "id": chart_id,
                        "type": "wind_rose",
                        "title": title or "风向玫瑰图（简化）",
                        "data": {
                            "sectors": sectors,
                            "legend": {
                                "N": "北风", "NE": "东北风", "E": "东风", "SE": "东南风",
                                "S": "南风", "SW": "西南风", "W": "西风", "NW": "西北风"
                            },
                            "statistics": {
                                "total_samples": len(data),
                                "avg_speed_overall": round(sum(s["avg_speed"] for s in sectors) / 8, 2),
                                "max_speed_overall": max(s["max_speed"] for s in sectors),
                                "dominant_direction": max(sectors, key=lambda x: x["frequency"])["direction"]
                            }
                        },
                        "meta": chart_meta
                    }
                except Exception as e:
                    logger.warning("wind_rose_fallback_failed", error=str(e))
                    # 继续到下一个检测

        # 2. 地图回退（map）
        if self._check_data_has_fields(data, ["longitude", "latitude"]):
            logger.info(
                "fallback_to_map",
                reason="检测到longitude和latitude字段"
            )

            if isinstance(data, list) and data:
                try:
                    # 计算地图中心
                    lngs = [item.get("longitude") for item in data if isinstance(item, dict) and item.get("longitude") is not None]
                    lats = [item.get("latitude") for item in data if isinstance(item, dict) and item.get("latitude") is not None]

                    if lngs and lats:
                        map_center = {
                            "lng": sum(lngs) / len(lngs),
                            "lat": sum(lats) / len(lats)
                        }
                    else:
                        map_center = {"lng": 114.05, "lat": 22.54}  # 默认深圳

                    # 构建标记点
                    markers = []
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        lng = item.get("longitude")
                        lat = item.get("latitude")
                        if lng is None or lat is None:
                            continue

                        marker = {
                            "lng": lng,
                            "lat": lat,
                            "name": item.get("name", item.get("station_name", "站点"))
                        }
                        if "value" in item:
                            marker["value"] = item["value"]
                        markers.append(marker)

                    return {
                        "id": chart_id,
                        "type": "map",
                        "title": title or "地图（简化）",
                        "data": {
                            "map_center": map_center,
                            "zoom": 12,
                            "layers": [
                                {
                                    "type": "marker",
                                    "data": markers,
                                    "visible": True
                                }
                            ]
                        },
                        "meta": chart_meta
                    }
                except Exception as e:
                    logger.warning("map_fallback_failed", error=str(e))
                    # 继续到下一个检测

        # 3. 热力图回退（heatmap） - 需要经纬度+数值
        if (self._check_data_has_fields(data, ["longitude", "latitude"]) and
            self._check_data_has_fields(data, ["value", "concentration", "pollutant"])):
            logger.info(
                "fallback_to_heatmap",
                reason="检测到经纬度和数值字段"
            )

            if isinstance(data, list) and data:
                try:
                    points = []
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        lng = item.get("longitude")
                        lat = item.get("latitude")
                        value = item.get("value") or item.get("concentration") or item.get("pollutant")

                        if lng is not None and lat is not None and value is not None:
                            try:
                                points.append({
                                    "lng": float(lng),
                                    "lat": float(lat),
                                    "value": float(value)
                                })
                            except (ValueError, TypeError):
                                continue

                    if points:
                        return {
                            "id": chart_id,
                            "type": "heatmap",
                            "title": title or "热力图（简化）",
                            "data": {
                                "points": points
                            },
                            "meta": {
                                **chart_meta,
                                "value_range": {
                                    "min": min(p["value"] for p in points),
                                    "max": max(p["value"] for p in points)
                                }
                            }
                        }
                except Exception as e:
                    logger.warning("heatmap_fallback_failed", error=str(e))
                    # 继续到下一个检测

        # 4. 3D散点图回退（scatter3d） - 需要x, y, z字段
        if self._check_data_has_all_fields(data, ["x", "y", "z"]):
            logger.info(
                "fallback_to_scatter3d",
                reason="检测到x, y, z字段"
            )

            if isinstance(data, list) and data:
                try:
                    x_data = []
                    y_data = []
                    z_data = []

                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        x = item.get("x")
                        y = item.get("y")
                        z = item.get("z")

                        if x is not None and y is not None and z is not None:
                            try:
                                x_data.append(float(x))
                                y_data.append(float(y))
                                z_data.append(float(z))
                            except (ValueError, TypeError):
                                continue

                    if x_data and y_data and z_data:
                        return {
                            "id": chart_id,
                            "type": "scatter3d",
                            "title": title or "3D散点图（简化）",
                            "data": {
                                "x": x_data,
                                "y": y_data,
                                "z": z_data
                            },
                            "meta": chart_meta
                        }
                except Exception as e:
                    logger.warning("scatter3d_fallback_failed", error=str(e))
                    # 继续到下一个检测

        # 5. 边界层廓线图回退（profile） - 需要altitude/height字段
        if self._check_data_has_fields(data, ["altitude", "height"]):
            logger.info(
                "fallback_to_profile",
                reason="检测到altitude或height字段"
            )

            if isinstance(data, list) and data:
                try:
                    # 提取高度和温度数据（简化版）
                    altitude_key = "altitude" if any("altitude" in item for item in data if isinstance(item, dict)) else "height"
                    altitudes = []
                    temperatures = []

                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        alt = item.get(altitude_key)
                        temp = item.get("temperature") or item.get("temp")

                        if alt is not None:
                            try:
                                altitudes.append(float(alt))
                                if temp is not None:
                                    temperatures.append(float(temp))
                                else:
                                    temperatures.append(None)
                            except (ValueError, TypeError):
                                continue

                    if altitudes:
                        return {
                            "id": chart_id,
                            "type": "profile",
                            "title": title or "边界层廓线图（简化）",
                            "data": {
                                "altitudes": altitudes,
                                "elements": [
                                    {
                                        "name": "温度",
                                        "unit": "°C",
                                        "data": temperatures
                                    }
                                ] if any(t is not None for t in temperatures) else []
                            },
                            "meta": chart_meta
                        }
                except Exception as e:
                    logger.warning("profile_fallback_failed", error=str(e))
                    # 继续到基础图表检测

        # ============================================
        # 原有基础图表检测逻辑
        # ============================================

        # 检测数据格式并生成相应图表
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            if isinstance(first_item, dict):
                keys = list(first_item.keys())

                # name/value -> 饼图
                if "name" in keys and "value" in keys:
                    return {
                        "id": chart_id,
                        "type": "pie",
                        "title": title or "饼图",
                        "data": data,
                        "meta": chart_meta
                    }

                # category/value -> 柱状图
                if "category" in keys and "value" in keys:
                    return {
                        "id": chart_id,
                        "type": "bar",
                        "title": title or "柱状图",
                        "data": {
                            "x": [item.get("category") for item in data],
                            "y": [item.get("value") for item in data]
                        },
                        "meta": chart_meta
                    }

        # 默认返回空柱状图
        return {
            "id": chart_id,
            "type": "bar",
            "title": title or "图表",
            "data": {"x": [], "y": []},
            "meta": {**chart_meta, "error": "数据格式无法识别"}
        }

    def _is_valid_chart_output(self, chart_dict: Dict[str, Any]) -> bool:
        """
        验证模板生成的图表输出是否有效

        检测常见的无效输出模式：
        - 空数据
        - 占位符数据（如 {"name": "Unknown", "value": 0}）
        - 缺少必需字段

        Args:
            chart_dict: 图表配置字典

        Returns:
            True if valid, False if invalid
        """
        if not isinstance(chart_dict, dict):
            logger.warning("chart_output_not_dict", type=type(chart_dict).__name__)
            return False

        # 检查必需字段
        if "id" not in chart_dict or "type" not in chart_dict or "data" not in chart_dict:
            logger.warning(
                "chart_output_missing_fields",
                missing=[f for f in ["id", "type", "data"] if f not in chart_dict]
            )
            return False

        chart_data = chart_dict.get("data")
        chart_type = chart_dict.get("type")

        # 检测占位符数据
        if chart_type == "pie":
            # 饼图：检查是否为空列表或占位符列表
            if isinstance(chart_data, list):
                if len(chart_data) == 0:
                    logger.warning("chart_output_empty_pie_data")
                    return False
                # 检测占位符：{"name": "Unknown", "value": 0}
                if any(
                    item.get("name") == "Unknown" and item.get("value") == 0
                    for item in chart_data if isinstance(item, dict)
                ):
                    logger.warning("chart_output_placeholder_pie_data")
                    return False

        elif chart_type in ["bar", "line"]:
            # 柱状图/折线图：检查x和y是否为空
            if isinstance(chart_data, dict):
                x_data = chart_data.get("x", [])
                y_data = chart_data.get("y", [])
                if len(x_data) == 0 or len(y_data) == 0:
                    logger.warning("chart_output_empty_bar_line_data")
                    return False

        elif chart_type == "timeseries":
            # 时序图：检查x和series
            if isinstance(chart_data, dict):
                x_data = chart_data.get("x", [])
                series_data = chart_data.get("series", [])
                if len(x_data) == 0 or len(series_data) == 0:
                    logger.warning("chart_output_empty_timeseries_data")
                    return False

        # 通过验证
        return True

    def _check_data_has_fields(self, data: Any, field_names: List[str]) -> bool:
        """
        检查数据是否包含指定字段（使用data_standardizer进行字段标准化）

        统一使用data_standardizer.py进行字段映射，避免出现字段不匹配的问题

        Args:
            data: 要检查的数据
            field_names: 字段名列表（任一存在即可）

        Returns:
            如果包含任一字段返回True，否则返回False
        """
        if not data or not field_names:
            return False

        # 使用全局data_standardizer进行字段标准化
        from app.utils.data_standardizer import get_data_standardizer
        standardizer = get_data_standardizer()

        # 如果是列表，检查第一个元素
        if isinstance(data, list):
            if not data:
                return False
            first_item = data[0]
            if isinstance(first_item, dict):
                # 检查是否包含任一字段（使用data_standardizer标准化后比较）
                for field in field_names:
                    # 检查原始字段名
                    if field in first_item:
                        return True
                    # 检查data_standardizer映射后的字段
                    for key in first_item.keys():
                        mapped_name = standardizer._get_standard_field_name(key)
                        if mapped_name == field:
                            return True
                return False
            return False

        # 如果是字典，检查字典本身或嵌套的data字段
        if isinstance(data, dict):
            # 检查顶层字段（使用data_standardizer标准化后比较）
            for field in field_names:
                # 检查原始字段名
                if field in data:
                    return True
                # 检查data_standardizer映射后的字段
                for key in data.keys():
                    mapped_name = standardizer._get_standard_field_name(key)
                    if mapped_name == field:
                        return True

            # 检查嵌套的data字段（如vocs_data、particulate_data等）
            for key, value in data.items():
                if isinstance(value, list) and value:
                    first_item = value[0]
                    if isinstance(first_item, dict):
                        # 检查嵌套字段（使用data_standardizer标准化后比较）
                        for field in field_names:
                            # 检查原始字段名
                            if field in first_item:
                                return True
                            # 检查data_standardizer映射后的字段
                            for nested_key in first_item.keys():
                                mapped_name = standardizer._get_standard_field_name(nested_key)
                                if mapped_name == field:
                                    return True

        return False

    def _check_data_has_all_fields(self, data: Any, field_names: List[str]) -> bool:
        """
        检查数据是否包含所有指定字段（使用data_standardizer进行字段标准化）

        与_check_data_has_fields的区别：
        - _check_data_has_fields: 检查任一字段存在（使用any()）
        - _check_data_has_all_fields: 检查所有字段都存在（使用all()）

        Args:
            data: 要检查的数据
            field_names: 字段名列表（必须全部存在）

        Returns:
            如果包含所有字段返回True，否则返回False
        """
        if not data or not field_names:
            return False

        # 使用全局data_standardizer进行字段标准化
        from app.utils.data_standardizer import get_data_standardizer
        standardizer = get_data_standardizer()

        # 如果是列表，检查第一个元素
        if isinstance(data, list):
            if not data:
                return False
            first_item = data[0]
            if isinstance(first_item, dict):
                # 检查是否包含所有字段（使用data_standardizer标准化后比较）
                for field in field_names:
                    found = False
                    # 检查原始字段名
                    if field in first_item:
                        found = True
                    else:
                        # 检查data_standardizer映射后的字段
                        for key in first_item.keys():
                            mapped_name = standardizer._get_standard_field_name(key)
                            if mapped_name == field:
                                found = True
                                break
                    if not found:
                        return False
                return True
            return False

        # 如果是字典，检查字典本身或嵌套的data字段
        if isinstance(data, dict):
            # 检查顶层字段（使用data_standardizer标准化后比较）
            for field in field_names:
                found = False
                # 检查原始字段名
                if field in data:
                    found = True
                else:
                    # 检查data_standardizer映射后的字段
                    for key in data.keys():
                        mapped_name = standardizer._get_standard_field_name(key)
                        if mapped_name == field:
                            found = True
                            break
                if not found:
                    return False

            # 检查嵌套的data字段（如vocs_data、particulate_data等）
            for key, value in data.items():
                if isinstance(value, list) and value:
                    first_item = value[0]
                    if isinstance(first_item, dict):
                        # 检查嵌套字段（使用data_standardizer标准化后比较）
                        all_found = True
                        for field in field_names:
                            field_found = False
                            # 检查原始字段名
                            if field in first_item:
                                field_found = True
                            else:
                                # 检查data_standardizer映射后的字段
                                for nested_key in first_item.keys():
                                    mapped_name = standardizer._get_standard_field_name(nested_key)
                                    if mapped_name == field:
                                        field_found = True
                                        break
                            if not field_found:
                                all_found = False
                                break
                        if all_found:
                            return True

        return False

    def _preprocess_data_for_simple_template(
        self,
        chart_type: str,
        data: Any
    ) -> Dict[str, Any]:
        """
        简化版数据预处理（适配简化版本的generate_chart工具）

        根据图表类型对数据进行基本预处理，不做复杂的兼容性检查和转换

        Args:
            chart_type: 图表类型
            data: 输入数据

        Returns:
            预处理后的数据
        """
        if not data:
            return {}

        # 通用场景：直接返回原始数据
        # 简化版本不进行复杂的预处理，让模板或LLM自己处理
        return data

    def _analyze_chart_data_validity(
        self,
        chart_dict: Dict[str, Any],
        original_data: Any
    ) -> Dict[str, Any]:
        """
        分析图表数据的有效性（用于LLM观测）

        检查图表生成过程中的数据质量，包括：
        - 数据点数量
        - null值比例
        - 数据结构正确性
        - 异常情况识别
        - 改进建议

        Args:
            chart_dict: 生成的图表配置
            original_data: 原始输入数据

        Returns:
            数据有效性分析结果
        """
        analysis_result = {
            "is_valid": True,
            "issue": "none",
            "data_point_count": 0,
            "null_count": 0,
            "null_percentage": 0.0,
            "structure": "unknown",
            "recommendation": ""
        }

        try:
            chart_type = chart_dict.get("type")
            chart_data = chart_dict.get("data")

            if not chart_data:
                analysis_result.update({
                    "is_valid": False,
                    "issue": "empty_chart_data",
                    "recommendation": "图表数据为空，请检查输入数据"
                })
                return analysis_result

            # 根据图表类型分析数据
            if chart_type == "timeseries":
                analysis_result["structure"] = "timeseries"
                if isinstance(chart_data, dict):
                    series_data = chart_data.get("series", [])
                    x_data = chart_data.get("x", [])

                    total_points = 0
                    null_points = 0

                    for series in series_data:
                        if isinstance(series, dict) and "data" in series:
                            data_list = series["data"]
                            total_points += len(data_list)
                            null_points += sum(1 for point in data_list if point is None)

                    analysis_result.update({
                        "data_point_count": total_points,
                        "null_count": null_points,
                        "null_percentage": round(null_points / total_points * 100, 2) if total_points > 0 else 0.0,
                        "series_count": len(series_data),
                        "time_points": len(x_data)
                    })

                    # 检查数据质量问题
                    if total_points == 0:
                        analysis_result.update({
                            "is_valid": False,
                            "issue": "no_data_points",
                            "recommendation": "时序数据为空，请检查原始数据"
                        })
                    elif total_points > 0 and null_points / total_points > 0.8:
                        analysis_result.update({
                            "is_valid": False,
                            "issue": "excessive_null_values",
                            "recommendation": f"超过80%的数据点为null（{analysis_result['null_percentage']:.1f}%），可能数据源问题"
                        })
                    elif total_points > 0 and null_points / total_points > 0.5:
                        analysis_result.update({
                            "is_valid": True,
                            "issue": "high_null_ratio",
                            "recommendation": f"约{analysis_result['null_percentage']:.1f}%的数据点为null，请确认数据完整性"
                        })

            elif chart_type in ["bar", "line"]:
                analysis_result["structure"] = "xy_data"
                if isinstance(chart_data, dict):
                    x_data = chart_data.get("x", [])
                    y_data = chart_data.get("y", [])

                    null_y = sum(1 for y in y_data if y is None) if y_data else 0

                    analysis_result.update({
                        "data_point_count": len(y_data),
                        "null_count": null_y,
                        "null_percentage": round(null_y / len(y_data) * 100, 2) if y_data else 0.0
                    })

                    if len(y_data) == 0:
                        analysis_result.update({
                            "is_valid": False,
                            "issue": "no_y_data",
                            "recommendation": "Y轴数据为空，请检查输入数据"
                        })
                    elif null_y == len(y_data):
                        analysis_result.update({
                            "is_valid": False,
                            "issue": "all_null_y_values",
                            "recommendation": "所有Y轴值都为null，可能数据源问题"
                        })

            elif chart_type == "pie":
                analysis_result["structure"] = "pie_data"
                if isinstance(chart_data, list):
                    null_values = sum(1 for item in chart_data if not isinstance(item, dict) or item.get("value") is None)
                    analysis_result.update({
                        "data_point_count": len(chart_data),
                        "null_count": null_values,
                        "null_percentage": round(null_values / len(chart_data) * 100, 2) if chart_data else 0.0
                    })

                    if len(chart_data) == 0:
                        analysis_result.update({
                            "is_valid": False,
                            "issue": "empty_pie_data",
                            "recommendation": "饼图数据为空"
                        })

            else:
                # 其他图表类型
                analysis_result["structure"] = f"chart_type_{chart_type}"
                if isinstance(chart_data, (dict, list)):
                    analysis_result["data_point_count"] = len(chart_data) if isinstance(chart_data, list) else 1

            # 原始数据检查
            if isinstance(original_data, list):
                original_count = len(original_data)
                analysis_result["raw_data_size"] = original_count

                if original_count == 0:
                    analysis_result.update({
                        "is_valid": False,
                        "issue": "empty_original_data",
                        "recommendation": "原始数据为空，无法生成有效图表"
                    })

        except Exception as e:
            logger.warning("data_analysis_failed", error=str(e))
            analysis_result.update({
                "is_valid": False,
                "issue": "analysis_error",
                "recommendation": f"数据分析失败: {str(e)}"
            })

        return analysis_result

    async def _generate_full_echarts_config(
        self,
        data: Dict[str, Any],
        chart_type: str,
        title: Optional[str],
        meta: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        生成完整的ECharts配置（增强版）

        支持：
        1. 完整的ECharts option对象生成
        2. 自定义配色方案
        3. 高级交互效果
        4. 响应式布局
        5. 自然语言样式描述理解

        Args:
            data: 数据
            chart_type: 图表类型
            title: 标题
            meta: 元数据

        Returns:
            图表配置或None（如果生成失败）
        """
        from app.services.llm_service import llm_service
        import json

        # 准备数据样本
        data_sample = json.dumps(data, ensure_ascii=False, indent=2)[:4000]

        # 构建增强版提示词
        enhanced_prompt = f"""
你是一个高级ECharts图表配置专家。请根据用户需求和示例数据，生成完整的ECharts配置代码。

# 需求
- 图表类型: {chart_type}
- 标题: {title or '自动生成'}
- 生成方式: 完整ECharts option对象（包含完整样式和交互）

# 数据样本
```json
{data_sample}
```

# ECharts配置要求

## 1. 完整option结构
返回完整的ECharts option对象，包含：
- title: 标题配置
- tooltip: 提示框配置
- legend: 图例配置
- grid: 网格配置
- xAxis/yAxis: 坐标轴配置
- series: 数据系列配置
- color: 配色方案
- animation: 动画配置

## 2. 高级特性
- **渐变色效果**: 使用ECharts渐变色配置
- **动画效果**: 添加加载动画、数据更新动画
- **交互特性**: 响应式缩放、数据筛选、钻取效果
- **布局优化**: 合理的间距、字体大小、颜色搭配

## 3. 配色方案（选择合适的）
- 科技蓝: #1e3a8a, #3b82f6, #60a5fa, #93c5fd
- 环保绿: #166534, #22c55e, #4ade80, #86efac
- 暖橙: #9a3412, #f97316, #fb923c, #fdba74
- 专业灰: #374151, #6b7280, #9ca3af, #d1d5db

## 4. Chart v3.1格式兼容
生成的配置必须适配前端Chart v3.1格式，包含：
- id: 图表ID
- type: 图表类型
- title: 图表标题
- data: ECharts option对象
- meta: 元数据（schema_version="3.1"）

## 5. 智能适配规则
- 如果数据包含时间字段，自动配置时间轴
- 如果数据包含多个系列，自动添加图例
- 如果数据值较大，自动调整Y轴刻度
- 如果是饼图，自动计算百分比并显示
- 如果是柱状图，按值降序排列

# 输出格式
返回JSON格式（不要markdown代码块）：
{{
    "id": "unique_chart_id",
    "type": "{chart_type}",
    "title": "{title or '图表标题'}",
    "data": {{
        // 完整的ECharts option对象
        "title": {{...}},
        "tooltip": {{...}},
        "legend": {{...}},
        "grid": {{...}},
        "xAxis": {{...}},
        "yAxis": {{...}},
        "series": [...],
        "color": [...],
        "animation": true,
        ...
    }},
    "meta": {{
        "schema_version": "3.1",
        "generator": "llm_enhanced",
        "scenario": "custom",
        "data_source": "generate_chart_llm_enhanced"
    }}
}}

# 重要提示
1. **只返回JSON**（不要markdown代码块，不要额外文字）
2. **确保option完整**：包含所有必需的ECharts配置项
3. **样式美观**：使用渐变色、动画、合理的布局
4. **交互友好**：支持鼠标悬停、点击、缩放等交互
5. **响应式设计**：适配不同屏幕尺寸

请直接返回JSON。
        """.strip()

        try:
            response = await llm_service.call_llm_with_json_response(enhanced_prompt)

            # 验证格式
            if "id" not in response or "type" not in response or "data" not in response:
                logger.warning(
                    "llm_enhanced_invalid_format",
                    missing_fields=[f for f in ["id", "type", "data"] if f not in response]
                )
                return None

            # 确保type匹配
            response["type"] = chart_type

            # 确保meta包含schema_version
            if "meta" not in response:
                response["meta"] = {}
            response["meta"]["schema_version"] = "3.1"
            response["meta"]["generator"] = "llm_enhanced"

            logger.info(
                "llm_enhanced_config_generated",
                chart_type=response.get("type"),
                chart_id=response.get("id")
            )

            return response

        except Exception as e:
            logger.warning(
                "llm_enhanced_generation_failed",
                chart_type=chart_type,
                error=str(e)
            )
            return None

    async def revise_chart(
        self,
        context: Any,
        original_chart_id: str,
        revision_instruction: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        修订已有图表（LLM驱动的多轮交互）

        支持场景：
        1. 修改图表类型（柱状图 → 饼图）
        2. 调整数据范围（仅显示TOP 10）
        3. 优化样式（修改颜色、标题）
        4. 增加元素（添加趋势线、标注）

        Args:
            context: 执行上下文
            original_chart_id: 原始图表的data_id（格式：chart_config:xxx）
            revision_instruction: 修订指令（自然语言）
            **kwargs: 额外参数

        Returns:
            UDF v2.0格式，包含修订后的图表（visuals字段）
        """
        try:
            # Step 1: 加载原始图表
            logger.info(
                "revise_chart_start",
                original_chart_id=original_chart_id,
                instruction=revision_instruction[:100]
            )

            try:
                # 获取原始图表配置
                original_chart_list = context.get_raw_data(original_chart_id)
                if not original_chart_list or not isinstance(original_chart_list, list):
                    return {
                        "status": "failed",
                        "success": False,
                        "data": None,
                        "metadata": {
                            "tool_name": "revise_chart",
                            "error_type": "invalid_chart_data",
                            "original_chart_id": original_chart_id
                        },
                        "summary": f"[FAIL] 原始图表数据无效: {original_chart_id}"
                    }

                # 提取ChartConfig的payload字段（实际图表配置）
                original_chart_config = original_chart_list[0]
                if hasattr(original_chart_config, 'payload'):
                    original_chart = original_chart_config.payload
                elif hasattr(original_chart_config, 'dict'):
                    original_chart_dict = original_chart_config.dict()
                    original_chart = original_chart_dict.get('payload', original_chart_dict)
                else:
                    original_chart = original_chart_config

                logger.info(
                    "original_chart_loaded",
                    chart_id=original_chart.get("id") if isinstance(original_chart, dict) else "unknown",
                    chart_type=original_chart.get("type") if isinstance(original_chart, dict) else "unknown"
                )

            except KeyError:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "revise_chart",
                        "error_type": "chart_not_found",
                        "original_chart_id": original_chart_id
                    },
                    "summary": f"[FAIL] 原始图表未找到: {original_chart_id}"
                }
            except Exception as exc:
                logger.error(
                    "original_chart_load_failed",
                    original_chart_id=original_chart_id,
                    error=str(exc)
                )
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "revise_chart",
                        "error_type": "chart_load_failed",
                        "original_chart_id": original_chart_id
                    },
                    "summary": f"[FAIL] 原始图表加载失败: {str(exc)}"
                }

            # 确保original_chart是字典
            if hasattr(original_chart, 'dict'):
                original_chart = original_chart.dict()
            elif hasattr(original_chart, 'model_dump'):
                original_chart = original_chart.model_dump()

            # Step 2: 构建修订提示词
            from app.services.llm_service import llm_service
            import json

            # 限制原始图表大小（避免超长prompt）
            original_chart_json = json.dumps(original_chart, ensure_ascii=False, indent=2)
            if len(original_chart_json) > 3000:
                original_chart_json = original_chart_json[:3000] + "\n... (已截断)"

            # 转义JSON中的花括号，避免.format()解析错误
            original_chart_json_escaped = original_chart_json.replace('{', '{{').replace('}', '}}')

            # 使用 .format() 代替 f-string 以避免嵌套括号问题
            revision_prompt = """
你是一个图表修订专家。用户请求修改已有图表，请根据修订指令生成新的图表配置。

# 原始图表配置（Chart v3.1格式）
```json
{original_chart_json}
```

# 修订指令
{revision_instruction}

# 修订要求

1. **保持格式一致**: 输出必须是完整的Chart v3.1格式，包含id/type/title/data/meta字段
2. **遵循指令**: 严格按照修订指令修改图表
3. **版本追踪**: 在meta中添加revision_count和revision_from字段
4. **数据完整性**: 如果修订涉及数据筛选（如TOP 10），确保data字段数据一致
5. **类型转换**: 如果修改图表类型，确保data字段格式匹配新类型

# Chart v3.1 支持的图表类型（15种）

## 基础图表
- pie: 饼图 - data格式: `[{{"name": "类别", "value": 数值}}, ...]`
- bar: 柱状图 - data格式: `{{"x": [类别], "y": [数值]}}`
- line: 折线图 - data格式: `{{"x": [时间], "y": [数值]}}`
- timeseries: 时序图 - data格式: `{{"x": [时间], "series": [{{"name": "系列", "data": [数值]}}]}}`
- radar: 雷达图 - data格式: `{{"dimensions": [维度], "series": [{{"name": "系列", "values": [数值]}}]}}`

## 气象图表
- wind_rose: 风向玫瑰图 - data格式: `{{"sectors": [{{"direction": "N", "avg_speed": 3.5}}]}}`
- profile: 边界层廓线图 - data格式: `{{"altitudes": [...], "elements": [{{"name": "温度", "data": [...]}}]}}`

## 空间图表
- map: 地图 - data格式: `{{"map_center": {{"lng": 114.05, "lat": 22.54}}, "layers": [...]}}`
- heatmap: 热力图 - data格式: `{{"points": [{{"lng": 114, "lat": 22, "value": 45}}]}}`

## 3D图表
- scatter3d: 3D散点图 - data格式: `{{"x": [...], "y": [...], "z": [...]}}`
- surface3d: 3D曲面图 - data格式: `{{"x": [...], "y": [...], "z": [[...]]}}`
- line3d: 3D线图 - data格式: `{{"x": [...], "y": [...], "z": [...]}}`
- bar3d: 3D柱状图 - data格式: `{{"x": [...], "y": [...], "z": [...]}}`
- volume3d: 3D体素图 - data格式: `{{"x": [...], "y": [...], "z": [...], "values": [[[]]]}}}`

# 修订示例

**示例1**: 修改图表类型
- 原始: 柱状图（bar）
- 指令: "改成饼图"
- 修订: type改为"pie"，data从`{{"x": [...], "y": [...]}}`转换为`[{{"name": x[i], "value": y[i]}}, ...]`

**示例2**: 数据筛选
- 原始: 包含50个类别的柱状图
- 指令: "只显示TOP 10"
- 修订: 按y值降序排列，截取前10个，更新data.x和data.y

**示例3**: 样式调整
- 原始: 标题"图表"
- 指令: "标题改为'污染物浓度对比'"
- 修订: title字段修改

# 版本追踪规则
- 首次修订: `"revision_count": 1, "revision_from": "原始图表ID"`
- 二次修订: `"revision_count": 2, "revision_from": "上一版图表ID"`

# 输出格式
返回完整的Chart v3.1 JSON（不要markdown代码块）：
{{
    "id": "新图表ID（使用revised_前缀）",
    "type": "图表类型",
    "title": "图表标题",
    "data": {{...}},
    "meta": {{
        "schema_version": "3.1",
        "generator": "revise_chart",
        "revision_count": 1,
        "revision_from": "原始图表ID",
        "revision_instruction": "修订指令简述",
        ...（保留原始meta中的其他字段）
    }}
}}

请直接返回JSON。
            """.strip().format(
                original_chart_json=original_chart_json,
                revision_instruction=revision_instruction
            )

            # Step 3: 调用LLM生成修订后的图表
            logger.info("calling_llm_for_revision", instruction_length=len(revision_instruction))
            try:
                revised_chart = await llm_service.call_llm_with_json_response(revision_prompt)

                # 验证v3.1格式
                if "id" not in revised_chart or "type" not in revised_chart or "data" not in revised_chart:
                    raise ValueError("LLM返回的修订图表不是有效的v3.1格式")

                # 确保meta中包含revision信息
                if "meta" not in revised_chart:
                    revised_chart["meta"] = {}
                revised_chart["meta"]["schema_version"] = "3.1"
                revised_chart["meta"]["generator"] = "revise_chart"
                if "revision_count" not in revised_chart["meta"]:
                    revised_chart["meta"]["revision_count"] = 1
                if "revision_from" not in revised_chart["meta"]:
                    revised_chart["meta"]["revision_from"] = original_chart.get("id", "unknown")

                logger.info(
                    "chart_revision_success",
                    revised_chart_id=revised_chart.get("id"),
                    revised_chart_type=revised_chart.get("type"),
                    revision_count=revised_chart["meta"].get("revision_count", 1)
                )

            except Exception as exc:
                logger.error(
                    "llm_revision_failed",
                    error=str(exc),
                    exc_info=True
                )
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "revise_chart",
                        "error_type": "llm_revision_failed",
                        "original_chart_id": original_chart_id
                    },
                    "summary": f"[FAIL] LLM修订失败: {str(exc)}"
                }

            # Step 4: 存储修订后的图表
            try:
                from datetime import datetime
                import uuid
                from app.schemas.chart import ChartConfig

                # 创建ChartConfig模型
                chart_config_model = ChartConfig(
                    chart_id=revised_chart.get("id", f"revised_{uuid.uuid4().hex[:8]}"),
                    chart_type=revised_chart.get("type", "custom"),
                    title=revised_chart.get("title", "修订图表"),
                    payload=revised_chart,
                    method="revision",
                    template_used=None,
                    scenario=revised_chart["meta"].get("scenario", "custom"),
                    data_record_count=revised_chart["meta"].get("record_count", 0),
                    pollutant=revised_chart["meta"].get("pollutant"),
                    station_name=revised_chart["meta"].get("station_name"),
                    venue_name=revised_chart["meta"].get("venue_name"),
                    generated_at=datetime.now().isoformat(),
                    metadata={
                        **revised_chart.get("meta", {}),
                        "format_version": "3.1",
                        "revision_from": original_chart_id,
                        "revision_instruction": revision_instruction[:200]
                    }
                )

                # 保存到context
                # save_data() 返回 {"data_id": str, "file_path": str}
                revised_chart_data_ref = context.save_data(
                    data=[chart_config_model],
                    schema="chart_config",
                    metadata={
                        "chart_type": chart_config_model.chart_type,
                        "method": "revision",
                        "revision_count": revised_chart["meta"].get("revision_count", 1),
                        "format_version": "3.1"
                    }
                )
                revised_chart_data_id = revised_chart_data_ref["data_id"]
                revised_chart_file_path = revised_chart_data_ref["file_path"]

                logger.info(
                    "revised_chart_saved",
                    data_id=revised_chart_data_id,
                    file_path=revised_chart_file_path,
                    chart_id=revised_chart.get("id")
                )

            except Exception as exc:
                logger.error(
                    "revised_chart_save_failed",
                    error=str(exc),
                    exc_info=True
                )
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "revise_chart",
                        "error_type": "chart_save_failed"
                    },
                    "summary": f"[FAIL] 修订图表保存失败: {str(exc)}"
                }

            # Step 5: 返回UDF v2.0格式（使用visuals字段）
            from app.schemas.unified import VisualBlock
            import uuid

            visual_block = VisualBlock(
                id=revised_chart.get("id", f"visual_{uuid.uuid4().hex[:8]}"),
                type="chart",
                schema="chart_config",
                payload=revised_chart,
                meta={
                    "source_data_ids": [revised_chart_data_id],
                    "schema_version": "v2.0",
                    "generator": "revise_chart",
                    "revision_count": revised_chart["meta"].get("revision_count", 1),
                    "revision_from": original_chart_id,
                    "layout_hint": "main"
                }
            )

            return {
                "status": "success",
                "success": True,
                "data": None,  # v2.0格式使用visuals字段
                "visuals": [visual_block.dict()],  # v2.0新增字段
                "metadata": {
                    "tool_name": "revise_chart",
                    "data_id": revised_chart_data_id,
                    "chart_type": revised_chart.get("type"),
                    "method": "revision",
                    "revision_count": revised_chart["meta"].get("revision_count", 1),
                    "original_chart_id": original_chart_id,
                    "schema_version": "v2.0",  # UDF v2.0 标记
                    "source_data_ids": [revised_chart_data_id],
                    "generator": "revise_chart",
                    "registry_schema": "chart_config"
                },
                "data_id": revised_chart_data_id,
                "file_path": revised_chart_file_path,
                "summary": f"✅ 图表修订完成（版本{revised_chart['meta'].get('revision_count', 1)}），类型: {revised_chart.get('type')} (UDF v2.0)"
            }

        except Exception as e:
            logger.error(
                "revise_chart_failed",
                original_chart_id=original_chart_id,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "tool_name": "revise_chart",
                    "error_type": "execution_failed",
                    "original_chart_id": original_chart_id
                },
                "summary": f"[FAIL] 图表修订失败: {str(e)[:50]}"
            }
