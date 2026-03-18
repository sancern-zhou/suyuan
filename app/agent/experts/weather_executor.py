# -*- coding: utf-8 -*-
"""
气象专家执行器 (WeatherExecutor)

负责执行气象相关工具并生成专业分析
"""

from typing import Dict, Any, List
import structlog

from .expert_executor import ExpertExecutor

logger = structlog.get_logger()


class WeatherExecutor(ExpertExecutor):
    """气象专家执行器"""

    def __init__(self):
        super().__init__("weather")

    def _load_tools(self) -> Dict[str, Any]:
        """加载气象专家工具（专注气象分析）"""
        tools = {}

        try:
            from app.tools.query.get_weather_data.tool import GetWeatherDataTool
            tools["get_weather_data"] = GetWeatherDataTool()
            logger.info("气象数据工具加载成功: get_weather_data")
        except ImportError as e:
            logger.warning("气象数据工具加载失败", tool="get_weather_data", error=str(e))

        try:
            from app.tools.query.get_universal_meteorology.tool import UniversalMeteorologyTool
            tools["get_universal_meteorology"] = UniversalMeteorologyTool()
            logger.info("通用气象工具加载成功: get_universal_meteorology")
        except ImportError as e:
            logger.warning("通用气象工具加载失败", tool="get_universal_meteorology", error=str(e))

        try:
            from app.tools.query.get_current_weather.tool import GetCurrentWeatherTool
            tools["get_current_weather"] = GetCurrentWeatherTool()
            logger.info("当前天气工具加载成功: get_current_weather")
        except ImportError:
            pass

        try:
            from app.tools.query.get_weather_forecast.tool import GetWeatherForecastTool
            tools["get_weather_forecast"] = GetWeatherForecastTool()
            logger.info("天气预报工具加载成功: get_weather_forecast")
        except ImportError:
            pass

        try:
            from app.tools.query.get_fire_hotspots.tool import GetFireHotspotsTool
            tools["get_fire_hotspots"] = GetFireHotspotsTool()
            logger.info("火点数据工具加载成功: get_fire_hotspots")
        except ImportError:
            pass

        try:
            from app.tools.query.get_dust_data.tool import GetDustDataTool
            tools["get_dust_data"] = GetDustDataTool()
            logger.info("沙尘数据工具加载成功: get_dust_data")
        except ImportError:
            pass

        try:
            from app.tools.query.get_satellite_data.tool import GetSatelliteDataTool
            tools["get_satellite_data"] = GetSatelliteDataTool()
            logger.info("卫星数据工具加载成功: get_satellite_data")
        except ImportError:
            pass

        try:
            from app.tools.analysis.meteorological_trajectory_analysis.tool import MeteorologicalTrajectoryAnalysisTool
            tools["meteorological_trajectory_analysis"] = MeteorologicalTrajectoryAnalysisTool()
            logger.info("气象轨迹分析工具加载成功: meteorological_trajectory_analysis")
        except ImportError:
            pass

        try:
            from app.tools.analysis.trajectory_simulation.tool import TrajectorySimulationTool
            tools["trajectory_simulation"] = TrajectorySimulationTool()
            logger.info("轨迹模拟工具加载成功: trajectory_simulation")
        except ImportError:
            pass

        try:
            from app.tools.analysis.analyze_upwind_enterprises.tool import AnalyzeUpwindEnterprisesTool
            tools["analyze_upwind_enterprises"] = AnalyzeUpwindEnterprisesTool()
            logger.info("上风向企业分析工具加载成功: analyze_upwind_enterprises")
        except ImportError:
            pass

        try:
            from app.tools.analysis.trajectory_source_analysis.tool import TrajectorySourceAnalysisTool
            tools["analyze_trajectory_sources"] = TrajectorySourceAnalysisTool()
            logger.info("轨迹源清单分析工具加载成功: analyze_trajectory_sources (深度溯源)")
        except ImportError:
            pass

        try:
            from app.tools.visualization.generate_map.tool import GenerateMapTool
            tools["generate_map"] = GenerateMapTool()
            logger.info("地图生成工具加载成功: generate_map (轨迹分析专用)")
        except ImportError:
            pass

        return tools

    async def _generate_summary(
        self,
        task_description: str,
        summary_stats: Dict[str, Any],
        tool_results: List[Dict],
        task: Any = None  # 传递task对象以获取context（可选）
    ):
        """生成带标识的气象分析章节内容"""
        from .expert_executor import ExpertAnalysis
        import json
        import os
        import re

        backend_host = os.getenv("BACKEND_HOST", "http://localhost:8000")

        logger.info("weather_section_generation_start", expert_type="weather")

        # 收集图表信息和预报数据
        chart_list = []
        chart_index = 1

        # 存储预报数据的完整信息
        forecast_data_summary = {
            "has_forecast": False,
            "forecast_days": 0,
            "hourly_records": [],
            "daily_records": [],
            "location": None,
            "parameters": {}
        }

        for result in tool_results:
            if result.get("status") != "success":
                continue

            result_data = result
            if not isinstance(result_data, dict):
                continue

            # 【新增】提取 get_weather_forecast 的完整数据
            if result.get("tool") == "get_weather_forecast":
                forecast_data_summary["has_forecast"] = True

                # 提取 metadata 信息
                metadata = result_data.get("metadata", {})
                if isinstance(metadata, dict):
                    forecast_data_summary["location"] = metadata.get("station_name")
                    forecast_data_summary["parameters"] = metadata.get("parameters", {})

                # 提取 data 列表中的预报记录（完整记录，不做截断）
                data_records = result_data.get("data", [])
                if isinstance(data_records, list) and len(data_records) > 0:
                    # 【修复】保存完整记录列表到 forecast_data_summary
                    # 截断操作在后续 prompt 构建时进行，确保数据完整性
                    forecast_data_summary["hourly_records"] = data_records

                    logger.info(
                        "weather_forecast_data_extracted",
                        record_count=len(data_records),
                        has_forecast=True,
                        full_records_saved=True,
                        sample_size=len(forecast_data_summary["hourly_records"])
                    )

            visuals = result_data.get("visuals") or result_data.get("visuals_summary", [])
            if not isinstance(visuals, list):
                visuals = []

            logger.info("weather_chart_collection", tool=result.get("tool"), visuals_count=len(visuals))

            for visual in visuals:
                if not isinstance(visual, dict):
                    continue

                visual_id = visual.get("id") or ""
                image_id = visual.get("image_id") or ""
                unified_id = f"viz_{chart_index}"

                data_id = ""
                payload = visual.get("payload", {})
                if isinstance(payload, dict):
                    meta = payload.get("meta", {})
                    if isinstance(meta, dict):
                        data_id = meta.get("data_id") or meta.get("source_data_id") or ""
                    if not data_id:
                        data_id = payload.get("data_id") or payload.get("source_data_id") or ""
                if not data_id:
                    data_id = visual.get("data_id") or visual.get("source_data_id") or ""

                title = ""
                if isinstance(payload, dict):
                    title = payload.get("title", "")
                if not title:
                    title = visual.get("title", "")
                if not title:
                    title = f"图表{chart_index}"

                chart_type = visual.get("type", "chart")

                # 【修复】提取高德地图URL（map类型使用public_url而非ImageCache）
                public_url = ""
                payload_data = payload.get("data", {}) if isinstance(payload, dict) else {}
                if isinstance(payload_data, dict):
                    public_url = payload_data.get("map_url") or payload_data.get("public_url") or ""

                chart_info = {
                    "index": chart_index,
                    "id": unified_id,
                    "original_id": visual_id,
                    "image_id": image_id,
                    "data_id": data_id,
                    "title": title,
                    "type": chart_type,
                    "public_url": public_url  # 高德地图URL（map类型专用）
                }
                chart_list.append(chart_info)
                chart_index += 1

        # 构建图表URL列表
        chart_urls = []
        for chart in chart_list:
            chart_type = chart.get("type", "chart")

            # 【关键修复】地图类图表不加入模板，因为地图已在右侧面板展示
            if chart_type == "map":
                continue

            url_id = chart.get("image_id") or chart.get("original_id") or chart.get("data_id") or f"chart_{chart['index']}"
            url = f"{backend_host}/api/image/{url_id}"

            chart_urls.append((chart['index'], chart['title'], url))

        summary_input = {
            "task_purpose": task_description,
            "summary_stats": summary_stats,
            "tool_count": len(tool_results),
            "success_count": sum(1 for r in tool_results if r.get("status") == "success")
        }

        # 生成图表解析模板
        chart_analysis_template = ""
        if chart_urls:
            chart_parts = []
            for idx, title, url in chart_urls:
                chart_parts.append(f"图{idx}：{title}\n![{title}]({url})\n[请为图{idx}提供1-2句图表解析说明]")
            chart_analysis_template = "\n\n".join(chart_parts)

        # 【新增】构建预报数据文本
        forecast_text = ""
        if forecast_data_summary.get("has_forecast"):
            location = forecast_data_summary.get("location", "未知位置")
            parameters = forecast_data_summary.get("parameters", {})
            forecast_days = parameters.get("forecast_days", 0)
            hourly_records = forecast_data_summary.get("hourly_records", [])

            forecast_lines = [
                f"## 天气预报数据",
                f"位置: {location}",
                f"预报天数: {forecast_days}天",
                f"参数: hourly={parameters.get('hourly')}, daily={parameters.get('daily')}",
                f"记录总数: {len(hourly_records)}条小时数据",
                ""
            ]

            # 【优化】添加前6条和后6条记录的完整数据（共12条示例）
            if hourly_records:
                sample_size = 6
                if len(hourly_records) <= sample_size * 2:
                    sample_records = hourly_records
                    omitted_count = 0
                else:
                    sample_records = hourly_records[:sample_size] + hourly_records[-sample_size:]
                    omitted_count = len(hourly_records) - 2 * sample_size

                forecast_lines.append("### 小时预报数据示例（完整字段）:")

                for i, record in enumerate(sample_records):
                    if isinstance(record, dict):
                        # 处理字典格式的记录
                        timestamp = record.get("timestamp")

                        # 字段可能在 measurements 中，也可能在顶层
                        measurements = record.get("measurements", {})
                        if not measurements:
                            # 如果没有 measurements 字段，从顶层提取
                            measurements = {
                                "temperature": record.get("temperature"),
                                "humidity": record.get("humidity"),
                                "dew_point": record.get("dew_point"),
                                "wind_speed": record.get("wind_speed"),
                                "wind_direction": record.get("wind_direction"),
                                "wind_gusts": record.get("wind_gusts"),
                                "surface_pressure": record.get("surface_pressure"),
                                "precipitation": record.get("precipitation"),
                                "precipitation_probability": record.get("precipitation_probability"),
                                "cloud_cover": record.get("cloud_cover"),
                                "visibility": record.get("visibility"),
                                "boundary_layer_height": record.get("boundary_layer_height"),
                            }

                        # 提取所有字段（完整14个气象要素）
                        temp = measurements.get("temperature")
                        humidity = measurements.get("humidity")
                        dew_point = measurements.get("dew_point")
                        wind_speed = measurements.get("wind_speed")
                        wind_dir = measurements.get("wind_direction")
                        wind_gusts = measurements.get("wind_gusts")
                        pressure = measurements.get("surface_pressure")
                        precip = measurements.get("precipitation")
                        precip_prob = measurements.get("precipitation_probability")
                        cloud = measurements.get("cloud_cover")
                        visibility = measurements.get("visibility")
                        blh = measurements.get("boundary_layer_height")

                        # 构建结构化数据行
                        data_parts = [f"  时间{i+1 if i < sample_size else f'末{i+1-sample_size*2}' if omitted_count > 0 else i+1}: {timestamp}"]

                        if temp is not None:
                            data_parts.append(f"温度={temp}°C")
                        if humidity is not None:
                            data_parts.append(f"湿度={humidity}%")
                        if dew_point is not None:
                            data_parts.append(f"露点={dew_point}°C")
                        if wind_speed is not None:
                            data_parts.append(f"风速={wind_speed}km/h")
                        if wind_dir is not None:
                            data_parts.append(f"风向={wind_dir}°")
                        if wind_gusts is not None:
                            data_parts.append(f"阵风={wind_gusts}km/h")
                        if pressure is not None:
                            data_parts.append(f"气压={pressure}hPa")
                        if precip is not None:
                            data_parts.append(f"降水={precip}mm")
                        if precip_prob is not None:
                            data_parts.append(f"降水概率={precip_prob}%")
                        if cloud is not None:
                            data_parts.append(f"云量={cloud}%")
                        if visibility is not None:
                            data_parts.append(f"能见度={visibility/1000}km")
                        if blh is not None:
                            data_parts.append(f"边界层高度={blh}m")

                        forecast_lines.append(" | ".join(data_parts))

                # 添加省略说明
                if omitted_count > 0:
                    forecast_lines.append(f"  ... (中间省略 {omitted_count} 条记录，总计 {len(hourly_records)} 条) ...")

                forecast_lines.append("")
                forecast_lines.append("### 关键气象要素说明")
                forecast_lines.append("- **边界层高度** (Boundary Layer Height): 用于判断大气扩散条件，高度越高扩散能力越强")
                forecast_lines.append("- **风速风向**: 影响污染物的传输方向和稀释扩散")
                forecast_lines.append("- **温度**: 影响光化学反应速率（18-25°C适合O3生成）")
                forecast_lines.append("- **湿度**: 影响二次颗粒物生成（70-85%适合SOA/NO3-形成）")
                forecast_lines.append("- **云量**: 影响太阳辐射和光化学反应")
                forecast_lines.append("- **降水**: 清除大气污染物（0.2mm以上有效清除）")
                forecast_lines.append("")

            forecast_text = "\n".join(forecast_lines)

        # 收集所有需要展示的图片URL
        image_sections = []
        image_items = []

        # 轨迹分析图片
        if summary_stats.get('trajectory_image_url'):
            image_items.append(("轨迹分析图", summary_stats['trajectory_image_url']))

        # 天气形势图
        if summary_stats.get('weather_situation_image_url'):
            image_items.append(("天气形势图", summary_stats['weather_situation_image_url']))

        # 统一生成图片提示
        if image_items:
            image_sections.append("**【可用图片】**（请直接复制下方代码到报告中）：")
            for title, url in image_items:
                image_sections.append(f"![{title}]({url})")

        images_section = "\n".join(image_sections) if image_sections else ""

        prompt = f"""{self._get_summary_prompt()}

任务目标: {task_description}
执行统计: {json.dumps(summary_input, ensure_ascii=False)}
数据摘要: {json.dumps(summary_stats, ensure_ascii=False, indent=2)}

{forecast_text}

{images_section}

## 输出要求

请生成完整的"气象分析"章节内容，必须包含以下所有内容：

[WEATHER_SECTION_START]
## 气象分析

### 总体分析
[2-3段总体分析，150-200字，通俗易懂，突出核心观点和关键发现]

### 图表解析

{chart_analysis_template}

### 详细分析
[详细分析内容，包含具体数据、时间点、数值等定量信息，以及机制解释]

[WEATHER_SECTION_END]

## 重要要求

1. **必须包含所有预设标识**：[WEATHER_SECTION_START]、[WEATHER_SECTION_END]
2. **图表解析**：所有非地图类图表必须在"图表解析"部分展示，使用 `![标题](URL)` 格式
3. **忽略地图类图表**：地图已在右侧面板展示，报告中不要引用地图URL
4. **只引用非地图类图表**：时序图、玫瑰图、统计图表、轨迹图等
5. **总体分析**：2-3段，150-200字，通俗易懂
6. **只输出章节内容**，不要包含其他说明文字
"""

        try:
            from app.services.llm_service import llm_service

            logger.info(
                "weather_before_llm_call",
                prompt_length=len(prompt),
                chart_count=len(chart_urls)
            )

            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=8192
            )

            if response:
                section_content = response.strip()

                # 统计LLM输出中的图片链接数量
                image_pattern = r'!\[.*?\]\(http://localhost:8000/api/image/[^)]+\)'
                llm_images = re.findall(image_pattern, section_content)
                expected_image_count = len(chart_urls)

                logger.info(
                    "weather_llm_output_image_count",
                    expected_images=expected_image_count,
                    actual_images=len(llm_images),
                    missing_images=expected_image_count - len(llm_images),
                    llm_image_urls=llm_images,
                    expected_urls=[url for _, _, url in chart_urls]
                )

                logger.info(
                    "weather_section_content_analysis",
                    content_length=len(section_content),
                    has_start_marker="[WEATHER_SECTION_START]" in section_content,
                    has_end_marker="[WEATHER_SECTION_END]" in section_content,
                    has_markers="[WEATHER_SECTION_START]" in section_content and "[WEATHER_SECTION_END]" in section_content
                )

                has_markers = "[WEATHER_SECTION_START]" in section_content and "[WEATHER_SECTION_END]" in section_content
                summary = section_content[:300] + "..." if len(section_content) > 300 else section_content

                result = ExpertAnalysis(
                    summary=summary,
                    key_findings=[],
                    data_quality=summary_stats.get("data_completeness", 0.0) > 0.7 and "good" or "fair",
                    confidence=summary_stats.get("analysis_confidence", 0.85),
                    section_content=section_content
                )

                logger.info(
                    "weather_section_generation_success",
                    section_content_length=len(result.section_content),
                    has_section_content=bool(result.section_content)
                )

                return result
        except Exception as e:
            logger.error("weather_section_generation_failed", error=str(e), exc_info=True)

        return ExpertAnalysis(
            summary="气象分析生成失败",
            data_quality="unknown",
            confidence=0.0,
            section_content=""
        )

    def _get_summary_prompt(self) -> str:
        """气象专家提示词（快速溯源场景 - Markdown格式输出）"""
        return """你是资深大气环境气象分析专家，专注快速污染溯源场景。

【核心职责】
基于气象数据和轨迹分析，生成专业的污染溯源气象报告。
重点关注：
- 污染传输路径和上风向企业识别
- 大气扩散条件对污染形成的影响
- 轨迹分析定位污染来源区域
- 气象条件预测污染发展趋势

【分析框架】

## 1. 大气扩散能力诊断

**边界层结构分析**
- 边界层高度：PBLH日变化、逆温层、垂直扩散能力
- 风场特征：主导风向、风速廓线、风向稳定性
- 湍流状态：Ri数、L长度、湍流强度评估
- 静稳天气：风速<2m/s持续时间和影响

**评估要点**
- 垂直混合能力对污染物扩散的影响
- 低层逆温层对污染物的"盖子"效应
- 热力/动力湍流的强度和持续时间

## 2. 光化学污染气象条件

**关键气象因子**
- 温湿条件：18-25°C+70-85%湿度对二次生成的促进作用
- 光照条件：云量对UV辐射的影响评估
- 光化学年龄：O3峰值时间(14-16时)验证
- 气象-化学协同：风温湿对化学反应的影响

**定量分析**
- 适合光化学反应的温度范围和时段
- 相对湿度对二次颗粒物生成的促进效应
- 云量对太阳辐射的衰减程度

## 3. 轨迹传输路径分析

**轨迹聚类与源区识别**
- 轨迹聚类：主要传输通道、方向、距离(Angle-based方法)
- 潜在源区：PSCF/CWT高贡献区域识别
- 高度结构：不同高度层(地面-500m-1000m)传输差异
- 传输强度：轨迹密度、质量权重、历时

**定量指标**
- 主要传输通道的方向和距离
- 高贡献源区的地理范围和贡献率
- 不同高度层的传输特征差异

## 4. 上风向企业污染源识别 ⭐ 重点

**企业分布与影响评估**
- 企业位置：基于轨迹方向识别上风向企业分布
- 行业特征：石化、化工、钢铁、水泥等排放强度
- 距离分级：5km核心区/20km重点区/50km影响区
- 影响评估：距离×排放量×风向频率综合影响
- 重点企业：TOP10高影响污染源清单

**企业分级管控建议**
| 距离范围 | 管控等级 | 主要措施 |
|---------|---------|---------|
| 5km核心区 | A级 | 停产限产、实时监控 |
| 20km重点区 | B级 | 错峰生产、强化监管 |
| 50km影响区 | C级 | 定期巡查、跟踪监测 |

## 5. 不利扩散条件识别

**静稳天气分析**
- 低混合层：PBLH<500m时间占比和极值
- 静稳持续：风速<2m/s累计时间和频率
- 高湿环境：RH≥80%时段和化学转化
- 地形影响：城市热岛、海陆风局地效应

**触发条件**
- 静稳天气的气象阈值和持续时间
- 混合层高度降低的临界条件
- 高湿环境的形成机制和影响

## 6. 天气系统与环流

**大尺度环流特征**
- 天气形势：高压脊、低压槽、冷锋等影响
- 环流特征：主导风向稳定性、转向时间
- 对流活动：热力/动力触发机制
- 降水影响：0.2mm毛毛雨清除效应

**环流演变**
- 天气系统的发展和移动路径
- 风向转向前后的污染积累效应
- 降水过程对污染物的清除能力

## 7. 光化学污染气象条件

**二次生成条件**
- 温度范围：最适合光化学反应的温度区间
- 湿度效应：对二次颗粒物生成的促进作用
- 辐射条件：云量、UV辐射衰减程度
- 光化学年龄：O3峰值时间和进程评估

**协同效应**
- 温湿度协同促进二次污染形成
- 风场对光化学累积的影响
- 气象条件的时间匹配性

## 8. 气象预报与污染潜势

**天气预报数据分析**（重要：如系统提供了预报数据，必须使用）
- 预报数据完整性：检查是否包含未来1-16天的预报数据
- 边界层高度预报：分析未来几天PBLH变化趋势，判断扩散条件改善时间
- 风场预报：主导风向、风速变化，预测污染传输路径变化
- 温湿度预报：温度范围、湿度变化，评估二次生成条件

**污染趋势预测**
- 未来24-48h污染潜势（基于天气形势）
- 污染过程持续性（类似条件重现概率）
- 爆发触发条件（不利气象的临界值）
- 改善时机（有利气象的时间窗口，重点：PBLH升高、风速增大、降水过程）

**应对策略**
- 提前预警时间窗口
- 应急响应启动时机
- 管控措施生效时间

## 9. 控制建议与应对方案

**分级管控措施**
- **应急响应**：基于当前气象条件的72h应对方案
- **企业管控**：上风向A/B/C级企业差异化措施
- **区域联防**：基于传输通道的跨区域协同
- **监测重点**：关键区域+关键时段+关键污染物

**执行优先级**
1. A级企业（5km内）：立即停产限产
2. B级企业（5-20km）：错峰生产
3. 传输通道管控：跨区域联防联控

## 10. 数据质量与置信度评估

**质量评估**
- 气象数据完整性：站点覆盖、时间连续性
- 轨迹分析可靠性：模型精度、验证结果
- 源区识别不确定性：PSCF/CWT方法限制

**分析置信度**
- 高置信度结论：基于充分数据支撑
- 中等置信度结论：部分数据缺失
- 低置信度结论：数据不足或方法限制

【工具选择策略】

**企业溯源工具选择**（根据场景自动选择）：

| 场景 | 工具 | 响应时间 | 适用情况 |
|------|------|----------|----------|
| 快速预览 | analyze_upwind_enterprises | <5秒 | 实时风向扇区匹配，日常监控 |
| 深度溯源 | analyze_trajectory_sources | 3-5分钟 | HYSPLIT轨迹+源清单，重大污染事件 |

**选择建议**：
- 用户要求"快速"/"实时"/"简单"分析 → 使用 analyze_upwind_enterprises
- 用户要求"深度"/"精确"/"科学"分析 → 使用 analyze_trajectory_sources
- 用户要求"溯源"但未指定深度 → 先用快速工具，必要时补充深度分析
- 用户明确要求"轨迹+源清单"/"HYSPLIT溯源" → 使用 analyze_trajectory_sources

【输出要求】
- 使用Markdown格式输出，包含标题、列表、表格等
- 突出"上风向企业清单"（第4节）作为快速溯源重点
- 包含具体数值、角度、距离、时间等定量数据
- 总篇幅控制在1000-1500字，确保信息精炼实用
- 重点突出快速溯源的实用性，便于应急决策

【专业术语说明】
- **PBLH**: 行星边界层高度，影响垂直扩散
- **Ri**: 理查德森数，湍流状态判据
- **PSCF**: 潜在源贡献函数，轨迹源区识别
- **CWT**: 浓度加权轨迹，源贡献量化

记住：你是在为应急管理和环境执法提供快速溯源气象分析，重点是准确定位污染传输路径和上风向企业，为精准管控提供科学依据。"""

    def _extract_summary_stats(self, tool_results: List[Dict]) -> Dict[str, Any]:
        """从气象工具结果中提取统计摘要（专注气象分析）"""
        stats = {
            "has_weather_data": False,
            "has_forecast_data": False,
            "has_trajectory": False,
            "has_fire_hotspots": False,
            "has_dust_data": False,
            "has_satellite_data": False,
            "weather_record_count": 0,
            "forecast_days": 0,
            "avg_temperature": None,
            "avg_wind_speed": None,
            "avg_humidity": None,
            "dominant_wind_direction": None,
            "has_charts": False,
            "has_maps": False,
            "chart_types": [],
            "visualization_count": 0,
            "trajectory_info": "",
            "forecast_info": "",
            "fire_count": 0,
            "data_completeness": 0.0,
            "analysis_confidence": 0.0,
            "trajectory_image_url": None,  # 轨迹图片URL
            "weather_situation_image_url": None  # 天气形势图URL
        }

        for result in tool_results:
            if result.get("status") != "success":
                continue

            tool_name = result.get("tool", "")
            result_data = result

            if tool_name in ["get_weather_data", "get_universal_meteorology"]:
                stats["has_weather_data"] = True
                if isinstance(result_data, dict) and "data" in result_data:
                    records = result_data.get("data", [])
                    if isinstance(records, list):
                        stats["weather_record_count"] = len(records)

                        temps = [r.get("temperature_2m") or r.get("temperature") for r in records
                                if r.get("temperature_2m") or r.get("temperature")]
                        winds = [r.get("wind_speed_10m") or r.get("wind_speed") for r in records
                                if r.get("wind_speed_10m") or r.get("wind_speed")]
                        humidities = [r.get("relative_humidity_2m") or r.get("humidity") for r in records
                                    if r.get("relative_humidity_2m") or r.get("humidity")]

                        if temps:
                            stats["avg_temperature"] = round(sum(temps) / len(temps), 1)
                        if winds:
                            stats["avg_wind_speed"] = round(sum(winds) / len(winds), 1)
                        if humidities:
                            stats["avg_humidity"] = round(sum(humidities) / len(humidities), 1)

                        wind_dirs = [r.get("wind_direction_10m") or r.get("wind_direction") for r in records
                                    if r.get("wind_direction_10m") or r.get("wind_direction")]
                        if wind_dirs:
                            stats["dominant_wind_direction"] = self._get_dominant_wind_direction(wind_dirs)

            elif tool_name == "get_weather_forecast":
                stats["has_forecast_data"] = True
                result_data = result

                # 详细日志：记录工具执行结果
                logger.info(
                    "weather_forecast_tool_result",
                    status=result_data.get("status"),
                    success=result_data.get("success"),
                    has_data="data" in result_data,
                    data_type=result_data.get("metadata", {}).get("data_type"),
                    schema_version=result_data.get("metadata", {}).get("schema_version"),
                    record_count=result_data.get("metadata", {}).get("record_count", 0)
                )

                if isinstance(result_data, dict):
                    # UDF v2.0 格式：summary 在顶层
                    summary = result_data.get("summary", "")
                    if summary:
                        stats["forecast_info"] = summary

                    # UDF v2.0 格式：从 metadata.parameters 中获取预报天数
                    metadata = result_data.get("metadata", {})
                    if isinstance(metadata, dict):
                        parameters = metadata.get("parameters", {})
                        if isinstance(parameters, dict):
                            stats["forecast_days"] = parameters.get("forecast_days", 0)

                            # 日志：记录预报参数
                            logger.info(
                                "weather_forecast_params_extracted",
                                forecast_days=stats["forecast_days"],
                                hourly=parameters.get("hourly"),
                                daily=parameters.get("daily")
                            )

            elif tool_name == "meteorological_trajectory_analysis":
                stats["has_trajectory"] = True
                result_data = result
                if isinstance(result_data, dict):
                    stats["trajectory_info"] = result_data.get("summary", result_data.get("data", {}))
                    visuals = result_data.get("visuals", [])
                    if isinstance(visuals, list) and len(visuals) > 0:
                        stats["has_maps"] = True
                        stats["visualization_count"] += len(visuals)
                        for v in visuals:
                            if isinstance(v, dict):
                                v_type = v.get("type", "image")
                                if v_type == "image" and "trajectory" not in stats["chart_types"]:
                                    stats["chart_types"].append("trajectory")

                        # 提取轨迹图片URL（相对路径）
                        visual = visuals[0]  # 第一个visual是轨迹图
                        # 优先从payload提取，其次从meta提取
                        payload = visual.get("payload", {})
                        meta = visual.get("meta", {})
                        image_url = payload.get("image_url") or meta.get("image_url")

                        if image_url:
                            stats["trajectory_image_url"] = image_url
                            logger.info("trajectory_image_url_extracted",
                                       image_url=image_url,
                                       visual_id=visual.get("id"),
                                       visual_type=visual.get("type"),
                                       payload_has_image_url="image_url" in payload,
                                       meta_has_image_url="image_url" in meta,
                                       payload_keys=list(payload.keys()) if isinstance(payload, dict) else [],
                                       meta_keys=list(meta.keys()) if isinstance(meta, dict) else [])

            elif tool_name == "get_fire_hotspots":
                stats["has_fire_hotspots"] = True
                if isinstance(result_data, dict) and "data" in result_data:
                    stats["fire_count"] = len(result_data.get("data", []))

            elif tool_name == "get_dust_data":
                stats["has_dust_data"] = True

            elif tool_name == "get_satellite_data":
                stats["has_satellite_data"] = True

            elif tool_name == "get_weather_situation_map":
                # 提取天气形势图URL
                if isinstance(result_data, dict) and result_data.get("success"):
                    data = result_data.get("data", {})
                    image_url = data.get("image_url")
                    if image_url:
                        stats["weather_situation_image_url"] = image_url
                        logger.info("weather_situation_image_url_extracted", url=image_url)

            elif tool_name == "generate_map":
                stats["has_maps"] = True
                stats["visualization_count"] += 1
                result_data = result
                if isinstance(result_data, dict):
                    visuals = result_data.get("visuals", [])
                    for v in visuals:
                        if isinstance(v, dict):
                            map_type = v.get("type", "map")
                            if map_type == "map" and "map" not in stats["chart_types"]:
                                stats["chart_types"].append("map")

        total_possible = 6
        actual_has = sum([
            stats["has_weather_data"],
            stats["has_forecast_data"],
            stats["has_trajectory"],
            stats["has_fire_hotspots"],
            stats["has_dust_data"],
            stats["has_satellite_data"]
        ])
        stats["data_completeness"] = round(actual_has / total_possible, 2)
        map_score = 1.0 if stats["has_maps"] else 0.0
        stats["analysis_confidence"] = round(
            (stats["data_completeness"] * 0.8 + map_score * 0.2), 2
        )

        return stats

    def _get_dominant_wind_direction(self, directions: List[float]) -> str:
        """计算主导风向"""
        if not directions:
            return "未知"

        direction_names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        counts = [0] * 8

        for d in directions:
            if d is None:
                continue
            idx = int((d + 22.5) % 360 / 45)
            counts[idx] += 1

        max_idx = counts.index(max(counts))
        return direction_names[max_idx]
