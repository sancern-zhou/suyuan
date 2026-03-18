"""
组分专家执行器 (ComponentExecutor)

负责执行污染物组分相关工具并生成专业分析
"""

from typing import Dict, Any, List, Optional
import structlog

from .expert_executor import ExpertExecutor
from app.utils.geo_matcher import get_geo_matcher

logger = structlog.get_logger()


class ComponentExecutor(ExpertExecutor):
    """组分专家执行器"""

    def __init__(self):
        super().__init__("component")
        self.geo_matcher = get_geo_matcher()

    def _build_geo_context(self, question: str) -> str:
        """
        从问题中提取地理信息并生成上下文

        Args:
            question: 用户问题

        Returns:
            格式化的地理上下文字符串
        """
        try:
            # 提取地理实体
            geo_entities = self.geo_matcher.extract_geo_entities(question)

            if not (geo_entities.get("has_venue") or geo_entities.get("has_city") or geo_entities.get("has_station")):
                return ""

            # 使用 GeoMatcher 的格式化方法
            geo_context = self.geo_matcher.format_for_llm(geo_entities)

            # 添加城市→站点映射信息
            if geo_entities.get("has_city"):
                cities = geo_entities.get("cities", [])
                station_mappings = self._get_city_station_mappings(cities)
                if station_mappings:
                    geo_context += "\n### 【站点映射】城市对应的监测站点：\n"
                    geo_context += station_mappings
                    geo_context += "\n**提示**: 以上为该城市可用的监测站点，请选择最合适的站点进行查询。\n"

            return geo_context

        except Exception as e:
            logger.warning("geo_context_extraction_failed", error=str(e))
            return ""

    def _get_city_station_mappings(self, cities: List[str]) -> str:
        """
        获取城市对应的站点映射信息

        Args:
            cities: 城市名称列表

        Returns:
            格式化的站点映射字符串
        """
        if not cities:
            return ""

        lines = []
        station_codes = self.geo_matcher.station_codes

        # 按城市分组站点
        city_stations = {}
        for station_name, code in station_codes.items():
            # 从 station_index 获取城市信息（如果有的话）
            station_data = self.geo_matcher.station_index.get(station_name)
            if station_data:
                city = station_data.get("city", "")
                if city in cities or f"{city}市" in cities:
                    if city not in city_stations:
                        city_stations[city] = []
                    city_stations[city].append(f"{station_name}({code})")

        # 格式化输出
        for city in cities:
            city_key = city.rstrip("市")
            if city_key in city_stations:
                stations = city_stations[city_key]
                lines.append(f"- **{city}**: {', '.join(stations)}")

        return "\n".join(lines) if lines else ""

    def _load_tools(self) -> Dict[str, Any]:
        """加载组分专家可用的工具"""
        tools = {}

        # ========================================
        # 气象数据工具（用于气象-污染协同分析）
        # ========================================
        try:
            from app.tools.query.get_weather_data.tool import GetWeatherDataTool
            tools["get_weather_data"] = GetWeatherDataTool()
            logger.info("气象数据工具加载成功: get_weather_data（用于气象-污染协同分析）")
        except ImportError as e:
            logger.warning("气象数据工具加载失败", tool="get_weather_data", error=str(e))

        # ========================================
        # 区域对比查询工具（优先级从高到低）
        # ========================================

        # 济宁市空气质量数据工具（最高优先级）
        try:
            from app.tools.query.get_jining_regular_stations.tool import GetJiningRegularStationsTool
            tools["get_jining_regular_stations"] = GetJiningRegularStationsTool()
            logger.info("济宁市区域对比工具加载成功: get_jining_regular_stations（端口9096）")
        except ImportError as e:
            logger.warning("济宁市区域对比工具加载失败", tool="get_jining_regular_stations", error=str(e))

        # 广东省空气质量数据工具（次高优先级）
        try:
            from app.tools.query.get_guangdong_regular_stations.tool import GetGuangdongRegularStationsTool
            tools["get_guangdong_regular_stations"] = GetGuangdongRegularStationsTool()
            logger.info("广东省区域对比工具加载成功: get_guangdong_regular_stations（端口9091）")
        except ImportError as e:
            logger.warning("广东省区域对比工具加载失败", tool="get_guangdong_regular_stations", error=str(e))

        # VOCs组分数据工具（端口9092）
        try:
            from app.tools.query.get_vocs_data.tool import GetVOCsDataTool
            tools["get_vocs_data"] = GetVOCsDataTool()
            logger.info("VOCs数据工具加载成功: get_vocs_data（端口9092）")
        except ImportError as e:
            logger.warning("VOCs数据工具加载失败", tool="get_vocs_data", error=str(e))

        # ========================================
        # 颗粒物组分工具（5个独立工具，参考项目模式）
        # ========================================
        try:
            from app.tools.query.get_pm25_ionic.tool import GetPM25IonicTool
            tools["get_pm25_ionic"] = GetPM25IonicTool()
            logger.info("颗粒物离子组分工具加载成功: get_pm25_ionic（F⁻、Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺等）")
        except ImportError as e:
            logger.warning("颗粒物离子组分工具加载失败", tool="get_pm25_ionic", error=str(e))

        try:
            from app.tools.query.get_pm25_carbon.tool import GetPM25CarbonTool
            tools["get_pm25_carbon"] = GetPM25CarbonTool()
            logger.info("颗粒物碳组分工具加载成功: get_pm25_carbon（OC/EC碳质组分）")
        except ImportError as e:
            logger.warning("颗粒物碳组分工具加载失败", tool="get_pm25_carbon", error=str(e))

        try:
            from app.tools.query.get_pm25_crustal.tool import GetPM25CrustalTool
            tools["get_pm25_crustal"] = GetPM25CrustalTool()
            logger.info("颗粒物地壳元素工具加载成功: get_pm25_crustal（铝、硅、钙、铁、钛、钾等）")
        except ImportError as e:
            logger.warning("颗粒物地壳元素工具加载失败", tool="get_pm25_crustal", error=str(e))

        try:
            from app.tools.query.get_particulate_components.tool import GetParticulateComponentsTool
            tools["get_particulate_components"] = GetParticulateComponentsTool()
            logger.info("PM2.5组分分析工具加载成功: get_particulate_components（Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、OC、EC）")
        except ImportError as e:
            logger.warning("PM2.5组分分析工具加载失败", tool="get_particulate_components", error=str(e))

        # ========================================
        # PM2.5专用组分分析工具（直接调用后端API）
        # ========================================
        try:
            from app.tools.query.get_pm25_component.tool import GetPM25ComponentTool
            tools["get_pm25_component"] = GetPM25ComponentTool()
            logger.info("PM2.5完整组分工具加载成功: get_pm25_component（32个因子）")
        except ImportError as e:
            logger.warning("PM2.5完整组分工具加载失败", tool="get_pm25_component", error=str(e))

        try:
            from app.tools.query.get_pm25_component.tool import GetPM25RecoveryTool
            tools["get_pm25_recovery"] = GetPM25RecoveryTool()
            logger.info("PM2.5重构分析工具加载成功: get_pm25_recovery（7大组分）")
        except ImportError as e:
            logger.warning("PM2.5重构分析工具加载失败", tool="get_pm25_recovery", error=str(e))

        try:
            from app.tools.query.get_pm25_component.tool import GetOCECTool
            tools["get_oc_ec"] = GetOCECTool()
            logger.info("OC/EC碳质分析工具加载成功: get_oc_ec")
        except ImportError as e:
            logger.warning("OC/EC碳质分析工具加载失败", tool="get_oc_ec", error=str(e))

        try:
            from app.tools.query.get_pm25_component.tool import GetHeavyMetalTool
            tools["get_heavy_metal"] = GetHeavyMetalTool()
            logger.info("重金属分析工具加载成功: get_heavy_metal")
        except ImportError as e:
            logger.warning("重金属分析工具加载失败", tool="get_heavy_metal", error=str(e))

        # 可选工具
        try:
            from app.tools.analysis.calculate_pm_pmf.tool import CalculatePMFTool
            tools["calculate_pm_pmf"] = CalculatePMFTool()
            logger.info("PMF工具加载成功: calculate_pm_pmf（颗粒物专用）")
        except ImportError:
            pass

        try:
            from app.tools.analysis.calculate_vocs_pmf.tool import CalculateVOCSPMFTool
            tools["calculate_vocs_pmf"] = CalculateVOCSPMFTool()
            logger.info("PMF工具加载成功: calculate_vocs_pmf（VOCs/臭氧专用）")
        except ImportError:
            pass

        # RACM2完整化学机理OBM分析工具 (102物种, 504反应)
        try:
            from app.tools.analysis.pybox_integration.tool import CalculateOBMFullChemistryTool
            tools["calculate_obm_full_chemistry"] = CalculateOBMFullChemistryTool()
            logger.info("RACM2完整化学机理工具加载成功: calculate_obm_full_chemistry")
        except ImportError as e:
            logger.warning("RACM2完整化学机理工具加载失败", tool="calculate_obm_full_chemistry", error=str(e))
        
        try:
            from app.tools.analysis.iaqi_calculator.tool import IAQICalculatorTool
            tools["iaqi_calculator"] = IAQICalculatorTool()
        except ImportError:
            pass

        # ========================================
        # 颗粒物组分分析工具（新增）
        # 7大组分重构、碳组分、地壳元素、水溶性离子、微量元素
        # ========================================
        try:
            from app.tools.analysis.calculate_reconstruction.calculate_reconstruction import CalculateReconstructionTool
            tools["calculate_reconstruction"] = CalculateReconstructionTool()
            logger.info("颗粒物组分工具加载成功: calculate_reconstruction（7大组分重构）")
        except ImportError as e:
            logger.warning("颗粒物组分工具加载失败", tool="calculate_reconstruction", error=str(e))

        try:
            from app.tools.analysis.calculate_carbon.calculate_carbon import CalculateCarbonTool
            tools["calculate_carbon"] = CalculateCarbonTool()
            logger.info("碳组分工具加载成功: calculate_carbon（碳组分分析）")
        except ImportError as e:
            logger.warning("碳组分工具加载失败", tool="calculate_carbon", error=str(e))

        try:
            from app.tools.analysis.calculate_crustal.calculate_crustal import CalculateCrustalTool
            tools["calculate_crustal"] = CalculateCrustalTool()
            logger.info("地壳元素工具加载成功: calculate_crustal（地壳元素分析）")
        except ImportError as e:
            logger.warning("地壳元素工具加载失败", tool="calculate_crustal", error=str(e))

        try:
            from app.tools.analysis.calculate_soluble.calculate_soluble import CalculateSolubleTool
            tools["calculate_soluble"] = CalculateSolubleTool()
            logger.info("水溶性离子工具加载成功: calculate_soluble（水溶性离子分析）")
        except ImportError as e:
            logger.warning("水溶性离子工具加载失败", tool="calculate_soluble", error=str(e))

        try:
            from app.tools.analysis.calculate_trace.calculate_trace import CalculateTraceTool
            tools["calculate_trace"] = CalculateTraceTool()
            logger.info("微量元素工具加载成功: calculate_trace（微量元素分析）")
        except ImportError as e:
            logger.warning("微量元素工具加载失败", tool="calculate_trace", error=str(e))

        try:
            from app.tools.analysis.ml_predictor.tool import MLPredictorTool
            tools["ml_predictor"] = MLPredictorTool()
        except ImportError:
            pass
        
        # ========================================
        # 可视化工具（v2.1新增 - 组分专家需要生成图表）
        # ========================================
        try:
            from app.tools.analysis.smart_chart_generator.tool import SmartChartGenerator
            tools["smart_chart_generator"] = SmartChartGenerator()
            logger.info("智能图表生成工具加载成功: smart_chart_generator")
        except ImportError as e:
            logger.warning("智能图表生成工具加载失败", tool="smart_chart_generator", error=str(e))
        
        try:
            from app.tools.visualization.generate_chart.tool import GenerateChartTool
            tools["generate_chart"] = GenerateChartTool()
            logger.info("图表生成工具加载成功: generate_chart")
        except ImportError as e:
            logger.warning("图表生成工具加载失败", tool="generate_chart", error=str(e))
        
        return tools
    
    async def _generate_summary(
        self,
        task_description: str,
        summary_stats: Dict[str, Any],
        tool_results: List[Dict],
        task: Any = None  # 传递task对象以获取context
    ):
        """生成带标识的组分分析章节内容"""
        from .expert_executor import ExpertAnalysis
        import json
        from structlog import get_logger
        import os
        import re

        logger = get_logger()
        backend_host = os.getenv("BACKEND_HOST", "http://localhost:8000")

        logger.info("component_section_generation_start", expert_type="component")

        # 收集图表信息
        chart_list = []
        chart_index = 1
        for result in tool_results:
            if result.get("status") != "success":
                continue
            # 【核心修复】扁平化结构：直接使用顶层result，不再嵌套result层
            result_data = result
            if not isinstance(result_data, dict):
                continue

            visuals = result_data.get("visuals") or result_data.get("visuals_summary", [])
            if not isinstance(visuals, list):
                visuals = []

            for visual in visuals:
                if not isinstance(visual, dict):
                    continue

                # 【核心修复】提取完整的图表标识信息
                # 【关键修复】统一ID格式：使用 viz_${index} 确保与前端 chartRefs key 一致
                # 后端: chart.id → /api/image/xxx (URL直接引用)
                # 前端: viz.id || `viz_${index}` → chartRefs[vizId]
                # 必须保持一致，否则图片无法匹配
                visual_id = visual.get("id") or ""
                image_id = visual.get("image_id") or ""
                # 统一使用 viz_${index} 格式，与前端 VisualizationPanel.vue 的 setChartRef 保持一致
                unified_id = f"viz_{chart_index}"

                # 提取 data_id（数据来源，用于关联）
                data_id = ""
                payload = visual.get("payload", {})
                if isinstance(payload, dict):
                    # 从 payload.meta 中获取 data_id
                    meta = payload.get("meta", {})
                    if isinstance(meta, dict):
                        data_id = meta.get("data_id") or meta.get("source_data_id") or ""
                    # 也检查 payload 顶层
                    if not data_id:
                        data_id = payload.get("data_id") or payload.get("source_data_id") or ""
                # 从 visual 顶层获取
                if not data_id:
                    data_id = visual.get("data_id") or visual.get("source_data_id") or ""

                # 提取图表标题
                title = ""
                if isinstance(payload, dict):
                    title = payload.get("title", "")
                if not title:
                    title = visual.get("title", "")
                if not title:
                    title = f"图表{chart_index}"

                # 提取图表类型
                chart_type = visual.get("type", "chart")

                # 提取 image_url 和 markdown_image（URL直接渲染方案）
                image_url = ""
                markdown_image = ""
                if isinstance(payload, dict):
                    image_url = payload.get("image_url") or ""
                    markdown_image = payload.get("markdown_image") or ""
                # 如果 payload 中没有，尝试从 visual.meta 获取
                if not image_url:
                    meta = visual.get("meta", {})
                    if isinstance(meta, dict):
                        image_url = meta.get("image_url") or ""
                        markdown_image = meta.get("markdown_image") or ""

                # 提取 image_id（图片格式）
                if chart_type == "image" or chart_type == "map":
                    if not image_id:
                        # 从 visual.data 中获取 image_id
                        visual_data = visual.get("data")
                        if isinstance(visual_data, str) and visual_data.startswith("data:image/"):
                            # 已经是完整的 data URL，提取 filename 作为 image_id
                            image_id = f"image_{chart_index}"
                        elif isinstance(visual_data, dict):
                            image_id = visual_data.get("image_id") or ""

                chart_info = {
                    "index": chart_index,
                    "id": unified_id,                  # ✅ 统一ID格式: viz_${index}，与前端 chartRefs key 一致
                    "original_id": visual_id,          # 保留原始visual.id供调试参考
                    "image_id": image_id,              # 图片ID（image_id）
                    "data_id": data_id,                # 数据来源ID
                    "title": title,
                    "type": chart_type,
                    "image_url": image_url,            # 完整图片URL
                    "markdown_image": markdown_image   # 预生成的Markdown格式
                }
                chart_list.append(chart_info)
                chart_index += 1

        # 提取工具数据
        tool_data_for_llm = self._extract_tool_data_for_llm(tool_results, max_records=20)

        # 构建图表列表文本（包含完整标识信息供LLM精准匹配）
        charts_text = ""
        if chart_list:
            charts_lines = ["可用图表列表（请直接使用Markdown图片链接插入图片）："]
            for chart in chart_list:
                # 【关键修复】包含 visual_id、image_id、data_id 供LLM精准匹配
                visual_id = chart.get("id", "")
                image_id = chart.get("image_id", "")
                data_id = chart.get("data_id", "")
                title = chart.get("title", "图表")

                # 构建标识字符串（优先使用 id > image_id > data_id）
                identifiers = []
                if visual_id:
                    identifiers.append(f"[ID:{visual_id}]")
                if image_id:
                    identifiers.append(f"[IMG:{image_id}]")
                if data_id:
                    identifiers.append(f"[DATA:{data_id}]")

                id_str = f" {' '.join(identifiers)}" if identifiers else ""

                # 获取或构建URL
                image_url = chart.get("image_url", "")
                if not image_url:
                    url_id = image_id or visual_id or data_id or f"chart_{chart['index']}"
                    image_url = f"{backend_host}/api/image/{url_id}"

                markdown_link = chart.get("markdown_image") or f"![{title}]({image_url})"

                charts_lines.append(f"图{chart['index']}{id_str}：{title}")
                charts_lines.append(f"   Markdown: {markdown_link}")
            charts_text = "\n".join(charts_lines)
        else:
            charts_text = "暂无图表"

        summary_input = {
            "task_purpose": task_description,
            "summary_stats": summary_stats,
            "tool_count": len(tool_results),
            "success_count": sum(1 for r in tool_results if r.get("status") == "success")
        }

        raw_data_section = ""
        if tool_data_for_llm:
            raw_data_section = f"""

【原始数据详情】
{json.dumps(tool_data_for_llm, ensure_ascii=False, indent=2)}

注意：如果数据标记为 truncated=true，表示数据已截断，原始记录数见 record_count。
"""

        # 根据工具执行结果和原始查询判断分析类型（优先使用原始pollutants）
        task_context = task.context if task else None
        analysis_type = self._get_analysis_type_from_results(tool_results, task_context)
        logger.info("component_analysis_type_detected", analysis_type=analysis_type,
                    pollutants=task_context.get("pollutants", []) if task_context else [])

        # 构建图表URL列表（供图表解析模板使用）
        chart_urls = []
        for chart in chart_list:
            image_url = chart.get("image_url", "")
            if not image_url:
                url_id = chart.get("image_id") or chart.get("original_id") or chart.get("data_id") or f"chart_{chart['index']}"
                image_url = f"{backend_host}/api/image/{url_id}"
            chart_urls.append((chart['index'], chart['title'], image_url))

        # 生成图表解析模板（参考气象专家方式）
        chart_analysis_template = ""
        if chart_urls:
            chart_parts = []
            for idx, title, url in chart_urls:
                chart_parts.append(f"""图{idx}：{title}
![{title}]({url})""")
            chart_analysis_template = "\n\n".join(chart_parts)

        # 提取地理上下文（新增）
        geo_context = self._build_geo_context(task_description)

        prompt = f"""{self._get_summary_prompt(analysis_type)}

{geo_context}
任务目标: {task_description}
执行统计: {json.dumps(summary_input, ensure_ascii=False)}
数据摘要: {json.dumps(summary_stats, ensure_ascii=False, indent=2)}
{raw_data_section}

## 图表信息
{charts_text}

## 输出要求（严格遵守）

请生成完整的"组分分析"章节内容，必须包含以下所有内容：

[COMPONENT_SECTION_START]
## 组分分析

### 总体分析
[2-3段总体分析，150-200字，通俗易懂，突出核心观点和关键发现]

### 图表解析
[为每一张图表生成Markdown图片链接和解析说明]

{chart_analysis_template}

**【URL验证规则】**
1. 必须在图表解析部分直接使用Markdown图片链接格式：`![图表标题](URL)`
2. URL必须与上方图表信息中的 **完整URL字符串** 完全一致，不能修改、截断或添加任何字符！
3. 图表数量必须与上方图表列表完全一致（当前{len(chart_urls)}张），不能遗漏任何一张！
4. 插入图片后立即提供1-2句简洁的解析说明，避免机械化表述

### 详细分析
[详细分析内容，包含具体数据、浓度值、贡献率等定量信息，以及化学机制解释]

[COMPONENT_SECTION_END]

## 重要要求

1. **必须包含所有预设标识**：[COMPONENT_SECTION_START]、[COMPONENT_SECTION_END]
2. **必须包含所有{len(chart_urls)}张图表**：每张图表都需要 **完整的Markdown图片链接** 和解析说明，缺一不可！
3. **URL一致性验证**：图片URL必须与上方图表信息中的完整URL字符串完全一致（精确到每个字符）
4. **图片插入**：使用Markdown图片链接格式 `![图表标题](URL)` 直接插入图片
5. **总体分析**：2-3段，150-200字，通俗易懂，避免技术术语堆砌
6. **图表解析**：为每个图表提供1-2句自然流畅的说明，避免"该图展示了"等机械化表述
7. **语言风格**：自然流畅的中文，符合专业报告但易于理解的风格
8. **只输出章节内容**，不要包含其他说明文字
9. **输出后自检**：必须验证Markdown链接数量等于{len(chart_urls)}张图表，且每个URL都与图表信息中的一致
"""
        
        try:
            from app.services.llm_service import llm_service

            # 【详细日志】记录调用LLM前的状态
            logger.info(
                "component_before_llm_call",
                prompt_length=len(prompt),
                prompt_preview=prompt[:300] + "..." if len(prompt) > 300 else prompt,
                summary_stats_keys=list(summary_stats.keys())
            )

            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=8192  # 确保完整输出，设置较大的token限制
            )

            # 【详细日志】记录LLM响应
            logger.info(
                "component_after_llm_call",
                has_response=bool(response),
                response_length=len(response) if response else 0,
                response_preview=(response[:200] + "..." if response and len(response) > 200 else response) if response else None
            )

            if response:
                # 提取章节内容
                section_content = response.strip()

                # 【修复】使用更宽松的正则表达式匹配图片URL（支持localhost、127.0.0.1、或任意host）
                image_pattern = r'!\[.*?\]\((?:http://(?:localhost|127\.0\.0\.1|[^)]+)/api/image/[^)]+)\)'
                llm_images = re.findall(image_pattern, section_content)
                expected_image_count = len(chart_urls)

                logger.info(
                    "component_llm_output_image_count",
                    expected_images=expected_image_count,
                    actual_images=len(llm_images),
                    missing_images=expected_image_count - len(llm_images),
                    llm_image_urls=llm_images,
                    expected_urls=[url for _, _, url in chart_urls]
                )

                # 【详细日志】分析section_content
                logger.info(
                    "component_section_content_analysis",
                    content_length=len(section_content),
                    content_type=type(section_content).__name__,
                    has_start_marker="[COMPONENT_SECTION_START]" in section_content,
                    has_end_marker="[COMPONENT_SECTION_END]" in section_content,
                    has_markers="[COMPONENT_SECTION_START]" in section_content and "[COMPONENT_SECTION_END]" in section_content,
                    content_preview=section_content[:500] + "..." if len(section_content) > 500 else section_content
                )

                # 检查是否包含预设标识
                has_markers = "[COMPONENT_SECTION_START]" in section_content and "[COMPONENT_SECTION_END]" in section_content
                logger.info(
                    "component_section_generated",
                    content_length=len(section_content),
                    has_markers=has_markers,
                    preview=section_content[:200] if section_content else ""
                )

                # 同时生成简短的summary用于兼容
                summary = section_content[:300] + "..." if len(section_content) > 300 else section_content

                result = ExpertAnalysis(
                    summary=summary,
                    key_findings=[],
                    data_quality=summary_stats.get("data_completeness", 0.0) > 0.7 and "good" or "fair",
                    confidence=summary_stats.get("analysis_confidence", 0.85),
                    section_content=section_content
                )

                # 【详细日志】确认ExpertAnalysis对象
                logger.info(
                    "component_expert_analysis_created",
                    analysis_type=type(result).__name__,
                    summary_length=len(result.summary),
                    section_content_length=len(result.section_content),
                    section_content_is_empty=not result.section_content,
                    section_content_preview=result.section_content[:200] + "..." if len(result.section_content) > 200 else result.section_content
                )

                logger.info(
                    "component_section_generation_success",
                    section_content_length=len(result.section_content),
                    has_section_content=bool(result.section_content)
                )

                return result
        except Exception as e:
            logger.error("component_section_generation_failed", error=str(e), exc_info=True)
        
        logger.warning("component_section_generation_fallback", reason="LLM调用失败或返回空")
        return ExpertAnalysis(
            summary="组分分析生成失败",
            data_quality="unknown",
            confidence=0.0,
            section_content=""
        )
    
    def _get_analysis_type_from_results(self, tool_results: List[Dict], context: Dict[str, Any] = None) -> str:
        """
        根据原始查询pollutants判断分析类型（PM vs O3）
        """
        # 从原始查询的pollutants判断
        pollutants = context.get("pollutants", []) if context else []
        if pollutants:
            # O3相关污染物 -> 臭氧分析
            ozone_related = ["O3", "臭氧", "VOCs", "VOC", "NOx", "NO2"]
            # PM相关污染物 -> 颗粒物分析
            pm_related = ["PM2.5", "PM10", "颗粒物", "PM"]

            is_ozone = any(p in pollutants for p in ozone_related)
            is_pm = any(p in pollutants for p in pm_related)

            if is_ozone:
                logger.info("analysis_type_from_pollutants", result="ozone", pollutants=pollutants)
                return "ozone"
            if is_pm:
                logger.info("analysis_type_from_pollutants", result="pm", pollutants=pollutants)
                return "pm"

        return "general"

    def _get_summary_prompt(self, analysis_type: str = "general") -> str:
        """组分专家总结提示词（根据分析类型选择差异化提示词）"""

        # 颗粒物溯源专用提示词
        PM_SUMMARY_PROMPT = """你是资深大气颗粒物化学分析专家，专精于PM2.5/PM10化学组分特征和颗粒物来源解析。

【核心职责】
基于颗粒物组分数据（水溶性离子、碳组分、地壳元素、微量元素等）和PMF源解析结果，生成专业的大气颗粒物污染诊断报告。
重点关注：
- 颗粒物化学组分特征和二次生成过程
- PMF源解析和主要贡献源识别（机动车尾气、工业排放、燃煤源、扬尘、生物质燃烧、二次硫酸盐/硝酸盐）
- 7大组分重构分析（OM、NO3、SO4、NH4、EC、地壳物质、微量元素）
- 颗粒物化学转化机制和来源解析

【分析框架】

1. **区域时序对比分析**（判断本地生成vs区域传输）
   - 目标与周边城市/站点的PM2.5/PM10浓度时序对比
   - 时间滞后相关性分析：判断传输方向和贡献大小
   - 峰值出现时间对比：周边先升高→区域传输；目标先升高→本地生成
   - 成因诊断结论：本地生成主导 / 区域传输主导 / 混合型

2. **颗粒物组分诊断**
   - 水溶性离子分析：硫酸盐、硝酸盐、铵盐的二次生成指示（SOR/NOR比值）
   - 碳组分分析：OC/EC比值判断一次排放 vs 二次有机碳
   - 地壳元素分析：Ca、Mg、Fe、Al等指示扬尘和土壤来源
   - 微量元素分析：Pb、Cd、As等指示工业排放和燃煤来源
   - 阴阳离子平衡：评估颗粒物酸碱度和中和状态

【颗粒物数据查询工具】

系统提供4个独立的颗粒物组分查询工具，分别对应不同类型的化学组分：

**参数说明（重要）**：
- 所有工具支持 `locations` 参数（推荐）：自动将城市/站点名称映射到站点编码
  - 示例：`{"locations": ["东莞"], "start_time": "...", "end_time": "..."}`
  - 支持站点名称：["东城", "新兴", "从化天湖"]
  - 支持城市名称：["广州", "深圳", "东莞"]（会自动映射到该城市的监测站点）
- 备选参数：`station` + `code`（直接指定站点名称和编码）

1. **get_particulate_components** - PM2.5综合组分分析（推荐用于PMF源解析）
   - 组分列表：Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、OC、EC
   - 参数：
     * locations: 站点/城市名称数组（推荐）
     * start_time/end_time: 时间范围（格式："YYYY-MM-DD HH:MM:SS"）
     * data_type: 数据类型（0=原始, 1=审计，默认0）
     * time_granularity: 时间粒度（1=小时, 2=日, 3=月, 5=年，默认1）
   - 特点：使用固定DetectionitemCodes清单，一次查询获取PMF所需的核心组分
   - 用于：PMF源解析（包含SO4、NO3、NH4、OC、EC等核心组分）

2. **get_pm25_ionic** - 水溶性离子组分（更全面的离子列表）
   - 组分列表：F⁻、Cl⁻、NO₂⁻、NO₃⁻、SO₄²⁻、PO₄³⁻、Li⁺、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、Al³⁺等
   - 参数格式同上
   - 用于：详细离子分析、二次气溶胶研究、阴阳离子平衡

3. **get_pm25_carbon** - 碳质组分（有机碳OC、元素碳EC）
   - 参数格式同上
   - 用于：碳组分分析、一次/二次有机碳分析

4. **get_pm25_crustal** - 地壳元素（铝Al、硅Si、钙Ca、铁Fe、钛Ti、钾K等）
   - 参数：elements（元素列表，可选，默认["Al", "Si", "Fe", "Ca", "Ti", "Mn"]）
   - 用于：扬尘源分析、土壤源识别

**PMF源解析建议**：
- **首选**：使用 get_particulate_components 一次获取所有核心组分（离子+碳组分）
- **备选**：同时调用 get_pm25_ionic 和 get_pm25_carbon 分别获取离子和碳组分
- 确保获取至少20个样本（time_granularity=1，且时间范围覆盖至少20个小时）
- **使用 locations 参数**：优先使用城市/站点名称，系统自动映射到正确的站点编码
  - 例如：`locations: ["广州"]` 会自动映射到广州的监测站点
  - 例如：`locations: ["东城"]` 会自动映射到站点编码 "1037b"

3. **PMF源解析深度分析**
   - 源因子识别：机动车尾气、工业排放、燃煤源、扬尘、生物质燃烧、二次硫酸盐、二次硝酸盐
   - 贡献率量化：各源类的浓度分担率和不确定性评估
   - 源谱特征：典型污染源的化学"指纹"识别
   - 时空变化：源贡献的日变化和区域差异
   - 【双模式交叉验证】：对比NNLS和NIMFA结果的一致性

4. **7大组分重构分析**
   - 有机物(OM)：估算有机碳的二次生成贡献
   - 硝酸盐(NO3-)：NO2氧化生成的二次颗粒物
   - 硫酸盐(SO42-)：SO2氧化生成的二次颗粒物
   - 铵盐(NH4+)：与硝酸盐、硫酸盐结合的中和剂
   - 元素碳(EC)：一次燃烧排放的示踪物
   - 地壳物质：土壤扬尘和建筑尘
   - 微量元素：工业排放和燃煤来源

5. **二次颗粒物生成评估**
   - 硝酸盐形成：NO2 + OH → HNO3，夜间NO3- + N2O5途径
   - 硫酸盐形成：SO2 + OH → H2SO4，液相氧化途径（金属催化）
   - SOA生成：生物源VOCs和人为VOCs的二次有机气溶胶
   - 温湿协同效应：18-25°C + 70-85%湿度促进二次颗粒物
   - SOR > 0.8表示硫酸盐以二次生成为主，NOR > 0.5表示硝酸盐以二次生成为主

6. **源贡献季节性变化**
   - 冬季采暖期：燃煤源和二次硫酸盐贡献增加
   - 夏季臭氧季：VOCs光化学产生的SOA增加
   - 干燥季节：扬尘贡献显著增加
   - 秸秆焚烧期：生物质燃烧源贡献突出

【专业输出格式】

**总体评估**
- 污染类型判定（一次排放主导/二次生成主导/混合型）
- 二次生成贡献占比（SO4^2-/NO3-/NH4+/SOA占总PM2.5的比例）
- 主要控制因子（前体物浓度/气象条件/化学反应/区域传输）
- 7大组分重构的闭合度（重构总和 vs 实测PM2.5）

**关键发现**（必须包含）
- 成因诊断：本地生成 vs 区域传输的判断及依据（基于周边城市/站点时序对比）
- 主要污染源贡献比例（PMF结果的具体数值，保留1位小数）
- 二次颗粒物生成比例：SOR值、NOR值、OC/EC比值
- 7大组分占比：OM%、NO3-%、SO42-%、NH4+%、EC%、地壳%、微量%
- 特征污染物：浓度最高的3种组分及其来源指示意义

**机制解释**
- 二次硫酸盐/硝酸盐的生成路径和限制因子（湿度、温度、光照、过渡金属）
- 不同源类的化学指纹特征（示踪化合物识别，如K+指示生物质燃烧）
- 气象条件对颗粒物生成和积累的影响机制
- 区域传输的通道和季节性特征

**控制建议**
- 一次排放控制：机动车/工业/扬尘/燃煤的减排优先级
- 二次前体物控制：SO2、NOx、VOCs、NH3的协同减排方案
- 区域联防：本地 vs 传输的差异化控制策略
- 应急措施：重污染天气下的临时管控建议

【专业术语库】
- SOR: 硫酸盐生成率，SOR>0.8表示二次生成主导
- NOR: 硝酸盐生成率，NOR>0.5表示二次生成主导
- OC/EC: 有机碳/元素碳比值，>2表明存在二次有机碳
- 7大组分：OM、NO3、SO4、NH4、EC、地壳、微量
- PMF: 正定矩阵因子分解，源解析方法
- NNLS/NIMFA: PMF的约束/非约束分解模式

【数据要求】
- PM2.5/PM10浓度：µg/m³
- 组分浓度：µg/m³（水溶性离子）、µg/m³（碳组分）、ng/m³（元素）
- 贡献率：百分比（%）
- 重构闭合度：重构总和/实测PM2.5 × 100%

【分析深度要求】
- 不仅要识别"是什么"，更要解释"为什么"和"如何形成"
- 定量分析：提供浓度、比率、贡献率等具体数值
- 化学机制：详细描述反应路径和动力学过程
- 溯源判断：基于化学指纹的污染源识别
- 控制策略：科学的前体物减排建议

记住：你是在为大气化学家和环境管理部门提供专业颗粒物诊断报告，每一个结论都要有化学机理支撑和数据分析基础。"""

        # 臭氧溯源专用提示词
        OZONE_SUMMARY_PROMPT = """你是资深大气光化学分析专家，专精于臭氧（O3）生成机制和前体物VOCs/NOx的敏感性分析。

【核心职责】
基于VOCs组分数据、常规污染物数据和OBM（观测box模型）分析结果，生成专业的大气光化学污染诊断报告。
重点关注：
- VOCs化学组分特征和臭氧生成潜势（OFP）
- OBM敏感性分析：VOCs控制型 vs NOx控制型
- PMF源解析：VOCs前体物的来源识别
- 光化学年龄和臭氧生成效率（OPE）

【分析框架】

1. **区域时序对比分析**（判断本地生成vs区域传输）
   - 目标与周边城市/站点的O3浓度时序对比
   - 时间滞后相关性分析：判断O3及其前体物的传输方向
   - 峰值出现时间对比：周边先升高→区域传输；目标先升高→本地光化学生成
   - 成因诊断结论：本地生成主导 / 区域传输主导 / 混合型

2. **VOCs组分诊断**
   - 碳氢化合物分类：烷烃、烯烃、芳香烃、含氧VOCs (OVOCs)、炔烃
   - 反应活性评估：基于MIR（最大增量反应活性）系数的OFP计算
   - 关键活性物种识别：对O3生成贡献最大的10个VOCs
   - 来源指示：异戊二烯（生物源）、乙炔（燃烧源）、苯系物（工业/溶剂）
   - 臭氧生成潜势(OFP)：各VOCs物种的OFP值和贡献排序

3. **PMF源解析深度分析**（VOCs前体物溯源）
   - 源因子识别：机动车尾气、石油化工、溶剂使用、燃烧源、工业过程、生物源
   - 贡献率量化：各源类对总VOCs和活性VOCs的贡献
   - 源谱特征：典型源的VOCs"指纹"（如C2-C5烷烃指示机动车）
   - 与OFP结合：识别高活性VOCs的主要来源

4. **OBM/OFP臭氧生成潜势分析**
   - VOCs活性评估：基于MIR系数的臭氧生成贡献排序
   - 敏感性诊断：VOCs控制型 vs NOx控制型的判断依据
   - EKMA曲线：绘制O3-VOCs-NOx敏感性曲面
   - 光化学年龄：VOCs/TVOCs比值和烷烃/烯烃比值估算
   - 控制策略：基于敏感性分析的前体物减排建议

5. **O3-NOx-VOCs敏感性分析**
   - VOCS-limited区域：削减VOCs可有效降低O3
   - NOx-limited区域：削减NOx可能导致O3升高（NO滴定效应）
   - Transitional区域：需要VOCs和NOx协同减排
   - RIR（相对反应性增量）分析：评估各物种对O3的敏感性贡献

6. **光化学进程分析**
   - 臭氧峰值时间：判断光化学反应的成熟度
   - O3生成速率：白天O3累积速度（µg/m³/h）
   - NO2峰值与O3峰值的时序关系
   - 前体物消耗与O3生成的对应关系

【专业输出格式】

**总体评估**
- 污染类型判定：VOCs控制型 / NOx控制型 / 过渡型
- 臭氧生成阶段：光化学年轻（峰值未到）/ 光化学成熟（峰值刚过）/ 光化学衰老
- 前体物限制：VOCs限制程度、NOx限制程度
- 关键控制因子：首要控制的VOCs物种类别和NOx

**关键发现**（必须包含）
- 成因诊断：本地光化学生成 vs 区域传输的判断及依据
- 主要VOCs来源贡献比例（PMF结果的具体数值）
- 臭氧生成潜势最高的5个VOCs物种（名称 + OFP值 + MIR值）
- O3生成敏感性类型（VOCs-limited/NOx-limited/transitional）
- 光化学年龄评估：VOCs/TVOCs比值和烷烃分布特征
- 关键活性物种的来源追踪（哪个源类贡献最大）

**机制解释**
- 为什么这些VOCs物种对O3生成贡献最大（分子结构和反应活性）
- VOCs与NOx的相对重要性及其空间/时间变化
- 气象条件（温度、光照、风速）对光化学反应的促进作用
- 区域传输对O3及其前体物浓度的影响

**控制建议**
- VOCs控制策略：针对高活性物种的减排优先级（如芳香烃、烯烃）
- NOx控制策略：基于敏感性分析的控制时机（避免NO滴定）
- 协同减排：VOCs和NOx的减排比例优化
- 区域联防：本地生成控制 vs 上风向传输拦截

【专业术语库】
- MIR: 最大增量反应活性，衡量VOCs生成O3的能力
- OFP: 臭氧生成潜势，单位µg/m³
- OPE: 臭氧生成效率，消耗单位VOCs生成的O3量
- RIR: 相对反应性增量，评估物种敏感性
- EKMA: 臭氧等浓度曲线，敏感性分析工具
- P(Ox): 总氧化剂产生速率
- L(VOC): VOCs的损失速率

【数据要求】
- VOCs浓度：ppbv或µg/m³
- OFP值：µg/m³
- MIR值：g O3/g VOCs
- 敏感性类型：VOCs-limited / NOx-limited / transitional
- 贡献率：百分比（%）

【分析深度要求】
- 不仅要识别"是什么"，更要解释"为什么"和"如何形成"
- 定量分析：提供浓度、活性、贡献率等具体数值
- 化学机制：详细描述光化学反应路径和自由基化学
- 溯源判断：基于VOCs指纹的污染源识别
- 控制策略：科学的前体物减排建议

记住：你是在为大气化学家和环境管理部门提供专业光化学诊断报告，每一个结论都要有化学机理支撑和数据分析基础。"""

        # 通用提示词（备用）
        GENERAL_SUMMARY_PROMPT = """你是资深大气污染化学分析专家，专精于污染物组分特征和大气化学过程分析。

【核心职责】
基于组分数据（VOCs、PM2.5/PM10颗粒物）和分析工具结果，生成专业的大气污染化学诊断报告。
重点关注：
- 污染物化学组分特征和二次生成过程
- PMF源解析和主要贡献源识别
- OBM/OFP臭氧生成潜势和敏感性分析
- 关键活性物种和反应机制

【分析框架】

1. **区域时序对比分析**（判断本地生成vs区域传输）
   - 目标与周边城市/站点的污染物浓度时序对比
   - 时间滞后相关性分析：判断传输方向和贡献大小
   - 峰值出现时间对比：周边先升高→区域传输；目标先升高→本地生成
   - 成因诊断结论：本地生成主导 / 区域传输主导 / 混合型

2. **污染物化学组分诊断**
   - VOCs组分分析：芳香烃、烷烃、烯烃、含氧VOCs的占比和活性
   - 颗粒物组分：硫酸盐、硝酸盐、铵盐、EC/OC的二次生成指示
   - 二次污染物识别：O3、NO3-、SO4^2-的形成机制
   - 化学转化过程：SO2→硫酸盐、NOx→硝酸盐的光化学和液相反应

【颗粒物数据查询工具】

系统提供4个独立的颗粒物组分查询工具：

**参数说明（重要）**：
- 推荐使用 `locations` 参数：`{"locations": ["城市/站点名"], "start_time": "...", "end_time": "..."}`
- 支持站点名称：["东城", "新兴", "从化天湖"]
- 支持城市名称：["广州", "深圳", "东莞"]（自动映射到监测站点）
- 备选参数：`station` + `code`

1. **get_particulate_components** - PM2.5综合组分分析（PMF推荐）
   - 查询：Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、OC、EC
   - 参数：locations, start_time, end_time, data_type, time_granularity
   - time_granularity: 1=小时, 2=日, 3=月, 5=年
   - 特点：一次获取PMF所需的核心组分（离子+碳组分）

2. **get_pm25_ionic** - 水溶性离子组分（更全面）
   - 查询：F⁻、Cl⁻、NO₂⁻、NO₃⁻、SO₄²⁻、PO₄³⁻、Li⁺、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、Al³⁺等
   - 参数格式同上

3. **get_pm25_carbon** - 碳质组分（OC/EC）
   - 查询：有机碳(OC)、元素碳(EC)
   - 参数格式同上

4. **get_pm25_crustal** - 地壳元素
   - 查询：铝Al、硅Si、钙Ca、铁Fe、钛Ti、钾K等
   - 参数：elements（可选，默认["Al", "Si", "Fe", "Ca", "Ti", "Mn"]）

**使用建议**：
- PMF分析（首选）：get_particulate_components 一次获取所有核心组分
- PMF分析（备选）：get_pm25_ionic + get_pm25_carbon 分别获取
- 扬尘分析：get_pm25_crustal
- **优先使用 locations 参数**，系统自动映射到正确的站点编码

3. **PMF源解析深度分析**
   - 源因子识别：工业排放、机动车尾气、燃烧源、二次形成等
   - 贡献率量化：各源类的浓度分担率和不确定性评估
   - 源谱特征：典型污染源的化学"指纹"识别
   - 时空变化：源贡献的日变化和区域差异

4. **OBM/OFP臭氧生成潜势分析**
   - VOCs活性评估：基于MIR系数的臭氧生成贡献排序
   - 关键物种识别：对O3生成贡献最大的10个VOCs物种
   - 敏感性诊断：VOCs控制型 vs NOx控制型的判断依据
   - 控制策略：基于敏感性分析的前体物减排建议

5. **二次颗粒物生成评估**
   - 硝酸盐形成：NO2 + OH → HNO3，夜间NO3- + N2O5途径
   - 硫酸盐形成：SO2 + OH → H2SO4，液相氧化途径
   - SOA生成：生物源VOCs和人为VOCs的二次有机气溶胶
   - 温湿协同效应：18-25°C + 70-85%湿度促进二次颗粒物

6. **化学反应机制诊断**
   - O3-NOx-VOCs循环：光化学反应的驱动机制
   - 自由基化学：OH、HO2、RO2自由基的浓度和反应速率
   - 夜间化学：NO3、N2O5的夜间化学反应
   - 液相化学：云雾滴和气溶胶表面的多相反应

【专业输出格式】

**总体评估**
- 污染类型判定（光化学污染/颗粒物污染/混合型）
- 二次生成贡献占比（一次排放% vs 二次生成%）
- 主要控制因子（前体物浓度/气象条件/化学反应）

**关键发现**（必须包含）
- 成因诊断：本地生成 vs 区域传输的判断及依据
- 主要污染源贡献比例（PMF结果的具体数值）
- 臭氧生成潜势最高的5个VOCs物种（名称 + MIR值）
- O3生成敏感性类型（VOCs-limited/NOx-limited/transitional）
- 二次颗粒物生成指示（SO4^2-/NO3-的比值和浓度）

**机制解释**
- 为什么这些VOCs物种对O3生成贡献最大
- 二次颗粒物的生成路径和限制因子
- 不同源类的化学指纹特征

**控制建议**
- VOCs控制策略：针对高活性物种的减排优先级
- NOx控制策略：基于敏感性分析的控制时机
- 颗粒物控制：前体物协同减排方案
- 区域联防：本地 vs 传输的差异化控制

记住：你是在为大气化学家和环境管理部门提供专业化学诊断报告，每一个结论都要有化学机理支撑和数据分析基础。"""

        # 根据分析类型选择提示词
        prompts = {
            "pm": PM_SUMMARY_PROMPT,
            "particulate": PM_SUMMARY_PROMPT,
            "pm_tracing": PM_SUMMARY_PROMPT,
            "ozone": OZONE_SUMMARY_PROMPT,
            "vocs": OZONE_SUMMARY_PROMPT,
            "o3": OZONE_SUMMARY_PROMPT,
            "ozone_tracing": OZONE_SUMMARY_PROMPT,
            "general": GENERAL_SUMMARY_PROMPT,
            "default": GENERAL_SUMMARY_PROMPT
        }

        prompt_key = analysis_type.lower() if isinstance(analysis_type, str) else "default"
        return prompts.get(prompt_key, prompts.get("default", GENERAL_SUMMARY_PROMPT))
    
    def _extract_summary_stats(self, tool_results: List[Dict]) -> Dict[str, Any]:
        """从组分工具结果中提取统计摘要"""
        
        stats = {
            "has_air_quality": False,
            "has_component": False,
            "has_pmf": False,
            "has_obm_ofp": False
        }

        for result in tool_results:
            if result.get("status") != "success":
                continue

            tool_name = result.get("tool", "")
            # 【核心修复】扁平化结构：直接使用顶层result，不再嵌套result层
            data = result

            if tool_name == "get_guangdong_regular_stations" or tool_name == "get_jining_regular_stations":
                stats["has_air_quality"] = True

                if isinstance(data, dict) and "data" in data:
                    records = data.get("data", [])
                    if records is None:
                        records = []
                    stats["record_count"] = len(records)

                    if records:
                        # 提取污染物平均浓度
                        pollutants = ["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"]
                        for p in pollutants:
                            key = p.lower().replace(".", "")
                            values = [r.get(p) or r.get(p.lower()) for r in records if r.get(p) or r.get(p.lower())]
                            if values:
                                values = [v for v in values if v is not None]
                                if values:
                                    stats[f"avg_{key}"] = round(sum(values) / len(values), 1)

                        # AQI
                        aqis = [r.get("AQI") or r.get("aqi") for r in records if r.get("AQI") or r.get("aqi")]
                        if aqis:
                            aqis = [a for a in aqis if a is not None]
                            if aqis:
                                stats["avg_aqi"] = round(sum(aqis) / len(aqis), 0)
                                stats["max_aqi"] = max(aqis)

            elif tool_name == "get_vocs_data":
                stats["has_component"] = True
                stats["component_type"] = "VOCs"

                # 安全地提取记录
                records = []
                if isinstance(data, dict) and "data" in data:
                    records = data.get("data", [])
                    if records is None:
                        records = []

                stats["component_record_count"] = len(records)
                stats["vocs_record_count"] = len(records)

                # 统计VOCs物种数量
                if records:
                    first_record = records[0] if records else {}
                    stats["vocs_species_count"] = len(first_record) if isinstance(first_record, dict) else 0

            elif tool_name == "get_particulate_data":
                stats["has_component"] = True
                stats["component_type"] = "PM_composition"

                # 安全地提取记录
                records = []
                if isinstance(data, dict) and "data" in data:
                    records = data.get("data", [])
                    if records is None:
                        records = []

                stats["component_record_count"] = len(records)
                stats["pm_record_count"] = len(records)
            
            elif tool_name in ["calculate_pm_pmf", "calculate_vocs_pmf"]:
                stats["has_pmf"] = True
                stats["pmf_tool_type"] = "vocs" if tool_name == "calculate_vocs_pmf" else "pm"

                if isinstance(data, dict):
                    # 【双模式支持】PMF工具返回结构:
                    # 单模式: {"data": result, "metadata": {...}}
                    # 双模式: {"data": {"nnls_result": {...}, "nimfa_result": {...}, ...}, "metadata": {...}}
                    pmf_data = data.get("data", data)  # 获取内层结果

                    # 安全检查：确保pmf_data不是None且是字典类型
                    if not isinstance(pmf_data, dict):
                        pmf_data = {}

                    # 判断是否为双模式
                    is_dual_mode = "nnls_result" in pmf_data

                    if is_dual_mode:
                        # 双模式：提取NNLS结果用于统计
                        nnls_result = pmf_data.get("nnls_result", {})
                        sources = nnls_result.get("sources", [])
                        source_contributions = nnls_result.get("source_contributions", {})
                        stats["pmf_analysis_mode"] = "dual"
                        stats["pmf_nimfa_factors"] = pmf_data.get("nimfa_result", {}).get("rank", 0)
                    else:
                        # 单模式：直接提取sources
                        sources = pmf_data.get("sources", [])
                        source_contributions = pmf_data.get("source_contributions", {})
                        stats["pmf_analysis_mode"] = "single"

                    # 提取源贡献信息（兼容两种模式）
                    if sources:
                        stats["pmf_factors"] = len(sources)
                        contributions = [(s.get("source_name"), s.get("contribution_pct", 0)) for s in sources]
                        contributions.sort(key=lambda x: x[1], reverse=True)
                        stats["top_sources"] = contributions[:3]
                        stats["main_source"] = contributions[0][0] if contributions else None
                        stats["main_contribution"] = contributions[0][1] if contributions else 0
                    elif source_contributions:
                        # 备用：直接从source_contributions字典提取
                        stats["pmf_factors"] = len(source_contributions)
                        sorted_contributions = sorted(source_contributions.items(), key=lambda x: x[1], reverse=True)
                        stats["top_sources"] = [(name, pct) for name, pct in sorted_contributions[:3]]
                        stats["main_source"] = sorted_contributions[0][0] if sorted_contributions else None
                        stats["main_contribution"] = sorted_contributions[0][1] if sorted_contributions else 0
            
        return stats
