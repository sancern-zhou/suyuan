"""
污染溯源报告生成工具

将 Expert V3 多专家溯源分析工作流改造为单一工具，直接生成 qmd 格式报告文档。
支持导出为 HTML 和 Word 格式。

核心功能：
- 完整保留 Expert V3 的多专家并行执行流程
- 封装为单一工具，LLM 可直接调用
- 生成图文并茂的 qmd 报告
- 支持导出 HTML/Word/PPTX 格式

依赖组件：
- ExpertRouterV3: 执行完整工作流
- QuartoReportRenderer: 渲染报告
- ChartImageRenderer: 渲染 ECharts 为 PNG
- ImageCache: 读取静态图片
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.path_config import get_reports_dir

logger = structlog.get_logger()


class GenerateTracingReportTool(LLMTool):
    """
    污染溯源报告生成工具

    直接生成 qmd 格式报告文档，支持 HTML/Word/PPTX 导出
    """

    def __init__(self):
        super().__init__(
            name="generate_tracing_report",
            description=(
                "生成污染溯源分析报告（qmd格式，支持HTML/Word/PPT导出）。"
                "这是一个完整的报告生成工具，会自动执行气象分析、组分分析、可视化和综合报告，"
                "并生成可直接下载的报告文档。适用于需要生成正式报告的场景。"
                "不要与 call_sub_agent 混淆，这是直接生成报告的工具。"
            ),
            category=ToolCategory.REPORTING,
            version="1.0.0",
            requires_context=False
        )

        # 初始化 ExpertRouterV3（延迟初始化）
        self._expert_router = None
        self._chart_renderer = None

        # 报告存储路径
        self.report_root = get_reports_dir()
        self.report_root.mkdir(parents=True, exist_ok=True)

    def get_function_schema(self) -> Dict[str, Any]:
        """获取工具函数定义"""
        return {
            "name": self.name,
            "description": (
                "生成污染溯源分析报告（qmd格式，支持HTML/Word/PPT导出）。"
                "这是一个一站式报告生成工具，内部会自动执行完整的专家分析流程（气象+组分+可视化+报告），"
                "并生成可直接下载的正式报告文档。"
                "\n\n"
                "使用场景："
                "- 用户明确要求'生成报告'、'制作报告'、'导出报告'"
                "- 需要正式的分析报告文档（而非简单的分析结果）"
                "- 需要包含图表、结论和建议的完整报告"
                "\n\n"
                "注意：不要与 call_sub_agent 混淆。"
                "- 如果用户只是询问分析结果，使用 call_sub_agent 调用专家模式"
                "- 如果用户明确要求生成报告，使用此工具"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用户查询（例如：'分析广州昨日O3污染溯源'）"
                    },
                    "precision": {
                        "type": "string",
                        "enum": ["fast", "standard", "full"],
                        "description": (
                            "分析精度："
                            "fast（快速~18秒）、"
                            "standard（标准~3分钟）、"
                            "full（完整~7-10分钟）"
                        )
                    }
                },
                "required": ["query"]
            }
        }

    @property
    def expert_router(self):
        """延迟初始化 ExpertRouterV3"""
        if self._expert_router is None:
            from app.agent.experts.expert_router_v3 import ExpertRouterV3
            from app.agent.memory.hybrid_manager import HybridMemoryManager

            # 创建临时会话ID和记忆管理器（用于 DataContextManager）
            temp_session_id = f"tracing_report_{uuid.uuid4().hex}"
            memory_manager = HybridMemoryManager(session_id=temp_session_id)

            self._expert_router = ExpertRouterV3(
                event_callback=None,  # 工具模式不需要事件回调
                memory_manager=memory_manager  # 必须提供，用于创建 DataContextManager
            )
        return self._expert_router

    @property
    def chart_renderer(self):
        """延迟初始化 ChartImageRenderer"""
        if self._chart_renderer is None:
            from app.tools.visualization.chart_image_renderer.tool import ChartImageRenderer
            self._chart_renderer = ChartImageRenderer()
        return self._chart_renderer

    async def execute(
        self,
        query: str,
        precision: str = "standard",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行报告生成

        Args:
            query: 用户查询
            precision: 分析精度（fast/standard/full）
            **kwargs: 其他参数

        Returns:
            Dict: 报告信息
                {
                    "success": True,
                    "data": {
                        "report_id": "tracing_report_20260510_abc123",
                        "preview_url": "/api/reports/{report_id}/html",
                        "download_urls": {
                            "html": "/api/reports/{report_id}/download/html",
                            "docx": "/api/reports/{report_id}/download/docx",
                            "pptx": "/api/reports/{report_id}/download/pptx"
                        },
                        "metadata": {...}
                    },
                    "summary": "..."
                }
        """
        logger.info(
            "tracing_report_generation_started",
            query=query[:100],
            precision=precision
        )

        try:
            # 1. 执行 Expert V3 流水线
            logger.info("executing_expert_v3_pipeline")
            pipeline_result = await self.expert_router.execute_pipeline(
                user_query=query,
                precision=precision,
                session_id=None  # 不需要会话恢复
            )

            if pipeline_result.status == "failed":
                return {
                    "success": False,
                    "error": "Expert V3 pipeline failed",
                    "errors": pipeline_result.errors
                }

            # 2. 创建报告目录
            report_id = f"tracing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            report_dir = self.report_root / report_id
            report_dir.mkdir(parents=True, exist_ok=True)

            assets_dir = report_dir / "assets" / "images"
            assets_dir.mkdir(parents=True, exist_ok=True)

            logger.info(
                "report_directory_created",
                report_id=report_id,
                report_dir=str(report_dir)
            )

            # 3. 处理图表（静态图片 + ECharts渲染）
            logger.info(
                "processing_visuals",
                total_visuals=len(pipeline_result.visuals)
            )
            processed_visuals = await self._process_visuals(
                pipeline_result.visuals,
                assets_dir
            )

            # 4. 生成 qmd 内容
            logger.info("generating_qmd_content")
            qmd_content = self._generate_qmd_content(
                pipeline_result,
                processed_visuals,
                report_id
            )

            # 4.5 修复图片路径：将 /api/image/xxx 替换为 assets/images/xxx.png
            # 并将所有引用的图片复制到本地 assets 目录
            qmd_content = self._fix_image_paths_in_content(qmd_content, assets_dir)

            # 5. 保存 qmd 文件
            qmd_path = report_dir / "report.qmd"
            qmd_path.write_text(qmd_content, encoding="utf-8")
            logger.info("qmd_file_saved", path=str(qmd_path))

            # 6. 保存元数据
            self._save_metadata(report_dir, pipeline_result, report_id)

            # 7. 渲染 HTML 预览
            logger.info("rendering_html_preview")
            try:
                from app.services.quarto_report_renderer import quarto_report_renderer
                quarto_report_renderer.render_preview_html(report_id)
                logger.info("html_preview_rendered")
            except Exception as e:
                logger.warning(
                    "html_preview_render_failed",
                    error=str(e)
                )

            # 8. 返回报告信息
            # 注意：DOCX/PPTX 是按需渲染（用户点击时才生成），不应提前返回链接
            return {
                "success": True,
                "data": {
                    "report_id": report_id,
                    "preview_url": f"/api/reports/{report_id}/html",
                    "download_urls": {
                        "html": f"/api/reports/{report_id}/download/html",
                    },
                    "render_on_demand_formats": ["docx", "pptx"],
                    "metadata": {
                        "location": pipeline_result.parsed_query.location if pipeline_result.parsed_query else "未知",
                        "precision": precision,
                        "experts": pipeline_result.selected_experts,
                        "confidence": pipeline_result.confidence,
                        "visuals_count": len(processed_visuals),
                        "created_at": datetime.now().isoformat()
                    }
                },
                "summary": (
                    f"[OK] 报告生成完成：{report_id}\n"
                    f"分析地点：{pipeline_result.parsed_query.location if pipeline_result.parsed_query else '未知'}\n"
                    f"参与专家：{', '.join(pipeline_result.selected_experts)}\n"
                    f"图表数量：{len(processed_visuals)}\n"
                    f"预览链接：{f'/api/reports/{report_id}/html'}\n"
                    f"Word 和 PPT 格式需在界面点击下载后才会生成"
                )
            }

        except Exception as e:
            logger.error(
                "tracing_report_generation_failed",
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def _process_visuals(
        self,
        visuals: List[Dict[str, Any]],
        assets_dir: Path
    ) -> List[Dict[str, Any]]:
        """
        处理图表（静态图片 + ECharts渲染）

        Args:
            visuals: 原始图表列表
            assets_dir: 资源目录

        Returns:
            List[Dict]: 处理后的图表列表
                {
                    "id": "图表ID",
                    "type": "static|echarts",
                    "title": "标题",
                    "image_path": "assets/images/xxx.png",
                    "relative_path": "assets/images/xxx.png"
                }
        """
        processed = []

        # 并发处理所有图表
        tasks = [
            self._process_single_visual(visual, assets_dir)
            for visual in visuals
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "visual_processing_failed",
                    error=str(result)
                )
                continue
            if result:
                processed.append(result)

        logger.info(
            "visuals_processed",
            total=len(visuals),
            successful=len(processed)
        )

        return processed

    async def _process_single_visual(
        self,
        visual: Dict[str, Any],
        assets_dir: Path
    ) -> Optional[Dict[str, Any]]:
        """
        处理单个图表

        Args:
            visual: 图表数据
            assets_dir: 资源目录

        Returns:
            Optional[Dict]: 处理后的图表信息
        """
        try:
            visual_id = visual.get("id")
            title = visual.get("title", "未命名图表")
            payload = visual.get("payload", {})
            meta = visual.get("meta", {})

            # Check map type first (before static/echarts classification)
            if self._is_map_visual(visual):
                return await self._process_map_visual(visual, assets_dir)

            #判断图表类型
            if self._is_static_image(visual):
                # 静态图片：直接复制
                return await self._copy_static_image(visual, assets_dir)
            else:
                # ECharts 配置：渲染为 PNG
                return await self._render_echarts_to_png(visual, assets_dir)

        except Exception as e:
            logger.warning(
                "single_visual_processing_failed",
                visual_id=visual.get("id"),
                error=str(e)
            )
            return None

    def _is_static_image(self, visual: Dict[str, Any]) -> bool:
        """
        判断是否为静态图片

        静态图片特征：
        - visual.id 是字符串且包含 "image_id"
        - visual.id 是字典且有 "image_id" 字段
        - payload.data 不包含 ECharts 关键字段

        Args:
            visual: 图表数据

        Returns:
            bool: 是否为静态图片
        """
        visual_id = visual.get("id")
        payload = visual.get("payload", {})

        # 检查 ID 特征
        if isinstance(visual_id, dict):
            if "image_id" in visual_id:
                return True
        elif isinstance(visual_id, str) and "image_id" in visual_id:
            return True

        # 检查 payload 特征
        data = payload.get("data", {})
        echarts_keywords = ["xAxis", "yAxis", "series", "dataset", "title"]

        # 如果包含 ECharts 关键字，认为是 ECharts 配置
        if any(keyword in data for keyword in echarts_keywords):
            return False

        # 默认认为是静态图片
        return True

    async def _copy_static_image(
        self,
        visual: Dict[str, Any],
        assets_dir: Path
    ) -> Optional[Dict[str, Any]]:
        """
        复制静态图片到报告目录

        Args:
            visual: 图表数据
            assets_dir: 资源目录

        Returns:
            Optional[Dict]: 处理后的图表信息
        """
        try:
            # 提取 image_id
            visual_id = visual.get("id")
            if isinstance(visual_id, dict):
                image_id = visual_id.get("image_id")
            elif isinstance(visual_id, str):
                # 从字符串中提取 image_id
                if "image_id" in visual_id:
                    image_id = visual_id
                else:
                    image_id = visual_id
            else:
                logger.warning("invalid_visual_id", visual_id=visual_id)
                return None

            # 从 ImageCache 读取图片
            from app.services.image_cache import image_cache
            image_bytes = image_cache.get_image_bytes(image_id)

            if not image_bytes:
                logger.warning("image_not_found", image_id=image_id)
                return None

            # 生成文件名
            file_extension = ".png"
            filename = f"{image_id}{file_extension}"
            dest_path = assets_dir / filename

            # 保存图片
            dest_path.write_bytes(image_bytes)

            # 提取专家信息（从 meta.generator 或 meta.scenario）
            meta = visual.get("meta", {})
            expert = self._extract_expert_from_meta(meta)

            return {
                "id": image_id,
                "type": "static",
                "title": visual.get("title", "未命名图表"),
                "image_path": str(dest_path),
                "relative_path": f"assets/images/{filename}",
                "expert": expert
            }

        except Exception as e:
            logger.warning(
                "static_image_copy_failed",
                error=str(e)
            )
            return None

    async def _render_echarts_to_png(
        self,
        visual: Dict[str, Any],
        assets_dir: Path
    ) -> Optional[Dict[str, Any]]:
        """
        渲染 ECharts 配置为 PNG

        Args:
            visual: 图表数据（v3.1格式）
            assets_dir: 资源目录

        Returns:
            Optional[Dict]: 处理后的图表信息
        """
        try:
            from app.utils.chart_v3_to_echarts_converter import get_chart_v3_converter

            # 提取图表数据（v3.1格式）
            payload = visual.get("payload", {})
            chart_type = visual.get("type", "")
            title = visual.get("title", "")
            meta = visual.get("meta", {})

            # 如果type是通用的"chart"，尝试从payload.data中获取具体类型
            if chart_type == "chart" or not chart_type:
                if isinstance(payload.get("data"), dict):
                    chart_type = payload["data"].get("type", "timeseries")  # 默认时序图
                else:
                    chart_type = "timeseries"

            chart_data = payload.get("data", {})

            # 如果chart_data有嵌套的type和data，提取实际的data
            if isinstance(chart_data, dict) and "data" in chart_data and "type" in chart_data:
                # 这是完整的ChartData对象，提取实际数据
                actual_data = chart_data.get("data")
                if actual_data:
                    chart_data = actual_data

            if not chart_data:
                logger.warning(
                    "empty_chart_data",
                    chart_type=chart_type,
                    visual_id=visual.get("id")
                )
                return None

            # 使用转换器将v3.1格式转换为ECharts配置
            converter = get_chart_v3_converter()
            echarts_option = converter.convert(
                chart_type=chart_type,
                chart_data=chart_data,
                title=title,
                meta=meta
            )

            if not echarts_option:
                logger.warning(
                    "echarts_conversion_failed",
                    chart_type=chart_type,
                    chart_data_keys=list(chart_data.keys()) if isinstance(chart_data, dict) else type(chart_data).__name__
                )
                return None

            # 生成缓存 key（基于转换后的ECharts配置的 hash）
            config_hash = hashlib.md5(
                json.dumps(echarts_option, sort_keys=True).encode()
            ).hexdigest()[:12]

            filename = f"echarts_{config_hash}.png"
            dest_path = assets_dir / filename

            # 创建简单的 context 对象（ChartImageRenderer 需要）
            class SimpleContext:
                pass

            context = SimpleContext()

            # 调用 ChartImageRenderer 渲染
            logger.info(
                "rendering_echarts_to_png",
                chart_type=chart_type,
                title=title,
                filename=filename
            )

            result = await self.chart_renderer.execute(
                context=context,
                echarts_option=echarts_option,
                width=1200,
                height=600
            )

            if not result.get("success"):
                logger.warning(
                    "echarts_render_failed",
                    result=result
                )
                return None

            # ChartImageRenderer 会生成自己的文件路径
            # 我们需要将文件复制到目标目录
            source_path = result.get("data", {}).get("image_path")
            if source_path:
                source_path = Path(source_path)
                if source_path.exists():
                    shutil.copy(source_path, dest_path)
                    logger.info(
                        "echarts_image_copied",
                        source=str(source_path),
                        dest=str(dest_path)
                    )
                else:
                    logger.warning("source_image_not_found", path=str(source_path))
                    return None

            # 提取专家信息（从 meta.generator 或 meta.scenario）
            meta = visual.get("meta", {})
            expert = self._extract_expert_from_meta(meta)

            return {
                "id": visual.get("id", f"echarts_{config_hash}"),
                "type": "echarts",
                "title": visual.get("title", "未命名图表"),
                "image_path": str(dest_path),
                "relative_path": f"assets/images/{filename}",
                "expert": expert,
                # 保留原始数据用于HTML报告渲染
                "chart_data": {
                    "type": chart_type,
                    "data": chart_data,
                    "title": title,
                    "meta": meta
                }
            }

        except Exception as e:
            logger.warning(
                "echarts_rendering_failed",
                error=str(e)
            )
            return None

    def _fix_image_paths_in_content(
        self,
        content: str,
        assets_dir: Path
    ) -> str:
        """
        修复 QMD 内容中的图片路径

        将所有 /api/image/xxx 或 (/api/image/xxx) 格式的路径替换为
        assets/images/xxx.png 相对路径，并确保图片文件存在于 assets 目录中。

        Args:
            content: QMD 文本内容
            assets_dir: 报告的 assets/images 目录

        Returns:
            str: 修复后的 QMD 内容
        """
        from app.services.image_cache import image_cache

        # 匹配 /api/image/xxx 格式（可能带或不带 .png 后缀）
        pattern = r'/api/image/([^\s\)\]"\']+)'
        matches = re.findall(pattern, content)

        copied_count = 0
        for image_id in set(matches):
            # 去掉可能的 .png 后缀
            clean_id = image_id.removesuffix('.png')

            filename = f"{clean_id}.png"
            dest_path = assets_dir / filename

            # 如果文件尚未存在，尝试从 image_cache 复制
            if not dest_path.exists():
                image_bytes = image_cache.get_image_bytes(clean_id)
                if image_bytes:
                    dest_path.write_bytes(image_bytes)
                    copied_count += 1
                    logger.info("image_copied_for_report", image_id=clean_id)
                else:
                    logger.warning("image_not_found_for_report", image_id=clean_id)

        # 替换所有路径：/api/image/xxx -> assets/images/xxx.png
        def replace_path(match):
            image_id = match.group(1)
            clean_id = image_id.removesuffix('.png')
            return f'assets/images/{clean_id}.png'

        fixed_content = re.sub(pattern, replace_path, content)

        logger.info(
            "image_paths_fixed_in_qmd",
            total_references=len(matches),
            unique_images=len(set(matches)),
            newly_copied=copied_count
        )

        return fixed_content

    def _extract_expert_from_meta(self, meta: Dict[str, Any]) -> str:
        """
        从 visual 的 meta 信息中提取专家类型

        Args:
            meta: 图表元数据

        Returns:
            str: 专家类型（weather/component/viz/report/unknown）
        """
        generator = meta.get("generator", "")
        scenario = meta.get("scenario", "")
        expert = meta.get("expert", "")

        # 直接有 expert 字段
        if expert:
            return expert

        # 从 generator 推断
        combined = f"{generator} {scenario}".lower()
        if any(k in combined for k in ["weather", "气象", "trajectory", "wind"]):
            return "weather"
        if any(k in combined for k in ["component", "组分", "ionic", "carbon", "crustal", "charge", "ec_oc", "pmf"]):
            return "component"
        if any(k in combined for k in ["viz", "可视化", "chart", "calendar", "timeseries", "stacked"]):
            return "viz"
        if any(k in combined for k in ["report", "报告", "upwind"]):
            return "report"

        return "unknown"

    def _is_map_visual(self, visual: Dict[str, Any]) -> bool:
        """
        Check if a visual is a map type.

        Args:
            visual: Visual data dict

        Returns:
            bool: True if visual type is "map"
        """
        return visual.get("type") == "map"

    async def _process_map_visual(
        self,
        visual: Dict[str, Any],
        assets_dir: Path
    ) -> Optional[Dict[str, Any]]:
        """
        Process a map-type visual:
        1. Render static PNG via Playwright (for DOCX/PPTX fallback)
        2. Return visual data for qmd HTML embedding

        Args:
            visual: Map visual data
            assets_dir: Assets directory

        Returns:
            Optional[Dict]: Processed map info with PNG path and map_data
        """
        try:
            payload = visual.get("payload", {})
            map_data = payload.get("data", {})

            # Validate required fields
            if not map_data.get("map_center") or not map_data.get("station"):
                logger.warning("invalid_map_data", visual_id=visual.get("id"))
                return None

            # Generate filename
            config_hash = hashlib.md5(
                json.dumps(map_data, sort_keys=True, default=str).encode()
            ).hexdigest()[:12]

            filename = f"map_{config_hash}.png"
            dest_path = assets_dir / filename

            # Render PNG via Playwright
            render_success = await self._render_map_to_png(
                map_data,
                str(dest_path),
                width=1200,
                height=700
            )

            if not render_success or not dest_path.exists():
                logger.warning("map_png_render_failed", visual_id=visual.get("id"))
                return None

            expert = self._extract_expert_from_meta(visual.get("meta", {}))

            return {
                "id": visual.get("id", f"map_{config_hash}"),
                "type": "map",
                "title": payload.get("title", "地图"),
                "image_path": str(dest_path),
                "relative_path": f"assets/images/{filename}",
                "map_data": map_data,
                "expert": expert
            }

        except Exception as e:
            logger.warning("map_visual_processing_failed", error=str(e))
            return None

    async def _render_map_to_png(
        self,
        map_data: Dict[str, Any],
        output_path: str,
        width: int = 1200,
        height: int = 700
    ) -> bool:
        """
        Render AMap configuration to PNG via Playwright.

        Args:
            map_data: AMap config (map_center, station, enterprises, etc.)
            output_path: Output PNG file path
            width: Image width
            height: Image height

        Returns:
            bool: True if successful
        """
        try:
            from playwright.async_api import async_playwright
            from config.settings import settings

            # Read AMap template
            # __file__ = .../tools/reporting/generate_tracing_report/tool.py
            # Need: .../tools/visualization/chart_image_renderer/amap_template.html
            template_dir = Path(__file__).parent.parent.parent / "visualization" / "chart_image_renderer"
            template_path = template_dir / "amap_template.html"
            if not template_path.exists():
                logger.error("amap_template_not_found", path=str(template_path))
                return False

            template_content = template_path.read_text(encoding="utf-8")

            amap_key = settings.amap_public_key or ""
            if not amap_key:
                logger.warning("amap_key_not_configured")
                return False

            config_json = json.dumps(map_data, ensure_ascii=False, default=str)

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                page = await browser.new_page(
                    viewport={"width": width + 40, "height": height + 40}
                )

                await page.set_content(template_content, wait_until="networkidle")

                # Inject config
                await page.evaluate(f"""
                    window.__AMAP_KEY__ = '{amap_key}';
                    window.__AMAP_CONFIG__ = {config_json};
                """)

                # Wait for map render
                await page.wait_for_function(
                    "window.__MAP_RENDERED__ === true",
                    timeout=20000
                )

                # Extra wait for tile loading
                await asyncio.sleep(1.5)

                # Screenshot
                container = page.locator('#amap-container')
                await container.screenshot(path=output_path, type="png")

                await browser.close()

            return True

        except ImportError:
            logger.error("playwright_not_installed_for_map")
            return False
        except Exception as e:
            logger.error("map_png_render_failed", error=str(e), exc_info=True)
            return False

    def _generate_map_html_block(
        self,
        visual_id: str,
        map_data: Dict[str, Any],
        amap_key: str
    ) -> str:
        """
        Generate a self-contained HTML block for interactive AMap embedding.

        Args:
            visual_id: Unique visual ID (for container ID)
            map_data: AMap config
            amap_key: AMap API key

        Returns:
            str: HTML block suitable for ```{=html} in qmd
        """
        container_id = f"amap_container_{re.sub(r'[^a-zA-Z0-9_-]', '_', str(visual_id))}"
        config_json = json.dumps(map_data, ensure_ascii=False, default=str)

        html = f"""
<div id="{container_id}" style="width:100%;height:550px;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);margin:1em 0;"></div>
<script>
(function() {{
    var config = {config_json};
    var containerId = '{container_id}';
    var amapKey = '{amap_key}';

    function initMap() {{
        if (typeof AMap === 'undefined') {{
            setTimeout(initMap, 200);
            return;
        }}

        var center = config.map_center;
        var map = new AMap.Map(containerId, {{
            center: [center.lng, center.lat],
            zoom: 12,
            viewMode: '2D',
            resizeEnable: true,
            features: ['bg', 'road', 'building', 'point'],
            mapStyle: 'amap://styles/normal'
        }});

        // Station marker
        var station = config.station || {{}};
        var stationLng = Number(station.lng || station.lon || station.longitude);
        var stationLat = Number(station.lat || station.latitude);
        if (stationLng && stationLat) {{
            var stationMarker = new AMap.Marker({{
                position: [stationLng, stationLat],
                title: station.name || '站点',
                zIndex: 100
            }});
            map.add(stationMarker);
        }}

        // Enterprise markers
        if (config.enterprises && Array.isArray(config.enterprises)) {{
            config.enterprises.forEach(function(ent, idx) {{
                var lng = Number(ent.lng || ent.lon || ent.longitude);
                var lat = Number(ent.lat || ent.latitude);
                if (!lng || !lat) return;

                var marker = new AMap.Marker({{
                    position: [lng, lat],
                    title: ent.name || '',
                    zIndex: 50
                }});
                map.add(marker);

                // Label for top 10 enterprises
                if (idx < 10) {{
                    var label = new AMap.Text({{
                        text: ent.name || '',
                        position: [lng, lat],
                        offset: [0, -35],
                        style: {{
                            'background-color': 'rgba(255,140,0,0.95)',
                            'border': '2px solid white',
                            'padding': '2px 6px',
                            'border-radius': '3px',
                            'font-size': '11px',
                            'color': 'white',
                            'white-space': 'nowrap'
                        }}
                    }});
                    map.add(label);
                }}
            }});
        }}

        // Upwind paths
        if (config.upwind_paths && Array.isArray(config.upwind_paths)) {{
            config.upwind_paths.forEach(function(path) {{
                if (!path.coordinates || path.coordinates.length < 2) return;
                var coords = path.coordinates.filter(function(c) {{
                    return typeof c.lng === 'number' && typeof c.lat === 'number';
                }}).map(function(c) {{ return [c.lng, c.lat]; }});
                if (coords.length >= 2) {{
                    map.add(new AMap.Polyline({{
                        path: coords,
                        strokeColor: '#FF4444',
                        strokeWeight: 4,
                        strokeOpacity: 1.0,
                        strokeStyle: 'dashed'
                    }}));
                }}
            }});
        }}

        // Wind sectors
        if (config.sectors && Array.isArray(config.sectors)) {{
            config.sectors.forEach(function(sector) {{
                if (!sector.coordinates || sector.coordinates.length < 3) return;
                var coords = sector.coordinates.filter(function(c) {{
                    return typeof c.lng === 'number' && typeof c.lat === 'number';
                }}).map(function(c) {{ return [c.lng, c.lat]; }});
                if (coords.length >= 3) {{
                    map.add(new AMap.Polygon({{
                        path: coords,
                        fillColor: '#4ECDC4',
                        fillOpacity: 0.3,
                        strokeColor: '#2BA89F',
                        strokeWeight: 2,
                        strokeOpacity: 0.7
                    }}));
                }}
            }});
        }}

        // Fit view
        map.setFitView(null, false, [50, 50, 50, 50]);
    }}

    // Load AMap SDK
    if (typeof AMap === 'undefined') {{
        var script = document.createElement('script');
        script.src = 'https://webapi.amap.com/maps?v=2.0&key=' + amapKey;
        script.onload = initMap;
        script.onerror = function() {{ console.error('Failed to load AMap SDK'); }};
        document.head.appendChild(script);
    }} else {{
        initMap();
    }}
}})();
</script>
""".strip()

        return html

    def _generate_echarts_html_block(
        self,
        visual_id: str,
        chart_data: Dict[str, Any]
    ) -> str:
        """
        Generate a self-contained HTML block for interactive ECharts embedding.

        Args:
            visual_id: Unique visual ID (for container ID)
            chart_data: v3.1 format chart data

        Returns:
            str: HTML block suitable for ```{=html} in qmd
        """
        container_id = f"echarts_container_{re.sub(r'[^a-zA-Z0-9_-]', '_', str(visual_id))}"
        chart_json = json.dumps(chart_data, ensure_ascii=False, default=str)

        html = f"""
<div id="{container_id}" style="width:100%;height:500px;margin:1em 0;"></div>
<script>
(function() {{
    var chartData = {chart_json};
    var containerId = '{container_id}';

    function initChart() {{
        if (typeof echarts === 'undefined') {{
            setTimeout(initChart, 200);
            return;
        }}

        var chartDom = document.getElementById(containerId);
        var myChart = echarts.init(chartDom);

        // 使用 v3.1 格式的图表数据
        // 前端的 ChartPanel.vue 会处理这种格式
        var option = {{
            title: {{
                text: chartData.title || '',
                left: 'center',
                textStyle: {{ fontSize: 16, fontWeight: 'bold' }}
            }},
            // 这里直接传递完整的v3.1数据，前端会转换
            // 暂时使用简化版本，前端需要完善支持
            tooltip: {{ trigger: 'axis' }},
            legend: {{ top: 55 }},
            grid: {{ top: 100, left: '3%', right: '4%', bottom: '3%', containLabel: true }}
        }};

        // 根据图表类型设置配置
        if (chartData.type === 'pie' && Array.isArray(chartData.data)) {{
            option.tooltip = {{ trigger: 'item', formatter: '{{b}}: {{c}} ({{d}}%)' }};
            option.legend = {{ orient: 'vertical', left: 'left', top: '10%' }};
            option.series = [{{
                type: 'pie',
                radius: ['40%', '70%'],
                center: ['50%', '60%'],
                data: chartData.data,
                label: {{ show: true, position: 'outside', formatter: '{{b}}: {{d}}%' }}
            }}];
        }} else if (chartData.type === 'bar' && chartData.data) {{
            option.xAxis = {{ type: 'category', data: chartData.data.x || [] }};
            option.yAxis = {{ type: 'value', name: chartData.meta?.unit || '' }};
            option.series = [{{
                type: 'bar',
                data: chartData.data.y || [],
                itemStyle: {{ color: '#5470c6' }}
            }}];
        }} else if (chartData.type === 'timeseries' && chartData.data) {{
            option.xAxis = {{ type: 'category', data: chartData.data.x || [], boundaryGap: false }};
            option.yAxis = {{ type: 'value', name: chartData.meta?.unit || '' }};
            option.series = (chartData.data.series || []).map(function(s, i) {{
                var colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272'];
                return {{
                    type: 'line',
                    name: s.name,
                    data: s.data,
                    smooth: true,
                    itemStyle: {{ color: colors[i % colors.length] }}
                }};
            }});
        }} else if (chartData.type === 'line' && chartData.data) {{
            option.xAxis = {{ type: 'category', data: chartData.data.x || [], boundaryGap: false }};
            option.yAxis = {{ type: 'value', name: chartData.meta?.unit || '' }};
            option.series = [{{
                type: 'line',
                data: chartData.data.y || [],
                smooth: true,
                areaStyle: {{ opacity: 0.1 }}
            }}];
        }}

        myChart.setOption(option);

        // 响应式
        window.addEventListener('resize', function() {{
            myChart.resize();
        }});
    }}

    // 加载 ECharts
    if (typeof echarts === 'undefined') {{
        var script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js';
        script.onload = initChart;
        script.onerror = function() {{ console.error('Failed to load ECharts'); }};
        document.head.appendChild(script);
    }} else {{
        initChart();
    }}
}})();
</script>
""".strip()

        return html

    def _filter_meta_cognitive_text(self, text: str) -> str:
        """
        过滤掉元认知文本（LLM的思考过程）

        Args:
            text: 原始文本

        Returns:
            str: 过滤后的文本
        """
        if not text:
            return text

        lines = text.split('\n')
        filtered_lines = []
        skip_mode = False

        meta_cognitive_patterns = [
            '嗯，用户要求我',
            '我需要先理解',
            '现在我需要处理',
            '让我仔细分析',
            '首先，快速理解',
            '在组织答案时',
            '我将生成如下',
            '让我分析这些数据以提取',
            '从查询结果来看',
            '等等，有些',
            '这看起来像',
            '让我理解',
            '我必须生成',
            '数据摘要显示'
        ]

        section_markers = [
            '## 气象分析',
            '## 组分分析',
            '## 结论与建议',
            '### 总体分析',
            '### 图表解析',
            '### 详细分析',
            '### 主要结论',
            '### 控制建议'
        ]

        for line in lines:
            stripped = line.strip()

            # 检查是否遇到正式章节标记
            if any(marker in stripped for marker in section_markers):
                skip_mode = False
                filtered_lines.append(line)
                continue

            # 如果在跳过模式，继续跳过
            if skip_mode:
                continue

            # 检查是否是元认知行
            is_meta_cognitive = any(pattern in stripped for pattern in meta_cognitive_patterns)

            if is_meta_cognitive:
                # 启动跳过模式
                skip_mode = True
                continue

            # 保留非空行和正式内容
            filtered_lines.append(line)

        return '\n'.join(filtered_lines)

    def _insert_enterprise_maps(
        self,
        content: str,
        visuals_by_expert: Dict[str, List[Dict[str, Any]]],
        amap_key: str
    ) -> str:
        """
        将企业分布地图插入到气象分析的图表解析部分

        Args:
            content: 原始内容
            visuals_by_expert: 按专家分组的图表
            amap_key: 高德地图API密钥

        Returns:
            str: 插入地图后的内容
        """
        # 获取 weather 专家的地图
        weather_visuals = visuals_by_expert.get("weather", [])
        enterprise_maps = [
            v for v in weather_visuals
            if v.get("type") == "map" and "enterprise" in v.get("title", "").lower()
        ]

        if not enterprise_maps:
            return content

        # 查找插入位置：在"图表解析"章节中的轨迹图之后
        lines = content.split('\n')
        result_lines = []
        inserted = False

        for i, line in enumerate(lines):
            result_lines.append(line)

            # 如果还没插入，且当前行是图表解析章节中的图片行
            if not inserted and 'trajectory' in line.lower() and '.png' in line:
                # 插入企业分布地图
                for map_visual in enterprise_maps[:1]:  # 只插入第一个地图
                    map_data = map_visual.get("map_data", {})
                    relative_path = map_visual.get("relative_path", "")

                    if amap_key and map_data:
                        # 生成交互式地图HTML
                        map_html = self._generate_map_html_block(
                            map_visual.get("id", "map"),
                            map_data,
                            amap_key
                        )
                        result_lines.append("\n#### 上风向企业分布\n\n")
                        result_lines.append('::: {.content-hidden when-format="docx"}\n\n')
                        result_lines.append('```{=html}\n')
                        result_lines.append(map_html + '\n')
                        result_lines.append('```\n\n')
                        result_lines.append(':::\n\n')
                        result_lines.append('::: {.content-hidden when-format="html"}\n\n')
                        result_lines.append(f"![企业分布地图]({relative_path})\n\n")
                        result_lines.append(':::\n\n')

                inserted = True

        return '\n'.join(result_lines)

    def _insert_echarts_charts(
        self,
        content: str,
        visuals_by_expert: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        将ECharts图表插入到综合分析章节

        Args:
            content: 原始内容
            visuals_by_expert: 按专家分组的图表

        Returns:
            str: 插入图表后的内容
        """
        # 获取所有ECharts图表
        echarts_visuals = []
        for expert, visuals in visuals_by_expert.items():
            for visual in visuals:
                if visual.get("type") == "echarts" and visual.get("chart_data"):
                    echarts_visuals.append(visual)

        if not echarts_visuals:
            return content

        # 在报告末尾（元数据之前）插入所有ECharts图表
        lines = content.split('\n')
        result_lines = []
        inserted = False

        for i, line in enumerate(lines):
            # 在元数据分隔线之前插入图表
            if not inserted and line.strip() == '---':
                # 插入ECharts图表章节
                result_lines.append("## 图表分析\n\n")

                for visual in echarts_visuals:
                    title = visual.get("title", "未命名图表")
                    chart_data = visual.get("chart_data", {})
                    relative_path = visual.get("relative_path", "")

                    result_lines.append(f"### {title}\n\n")

                    # HTML格式：交互式ECharts图表
                    result_lines.append('::: {.content-hidden when-format="docx"}\n\n')
                    echarts_html = self._generate_echarts_html_block(
                        visual.get("id", "echarts"),
                        chart_data
                    )
                    result_lines.append('```{=html}\n')
                    result_lines.append(echarts_html + '\n')
                    result_lines.append('```\n\n')
                    result_lines.append(':::\n\n')

                    # Word/PPT格式：静态PNG图片
                    result_lines.append('::: {.content-hidden when-format="html"}\n\n')
                    result_lines.append(f"![{title}]({relative_path})\n\n")
                    result_lines.append(':::\n\n')

                inserted = True

            result_lines.append(line)

        return '\n'.join(result_lines)

    def _generate_simplified_analysis(
        self,
        pipeline_result,
        visuals_by_expert: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        生成简化的综合分析章节

        Args:
            pipeline_result: Expert V3 执行结果
            visuals_by_expert: 按专家分组的图表

        Returns:
            str: Markdown 内容
        """
        content = "## 综合分析\n\n"

        # 获取 report 专家的响应
        report_result = pipeline_result.expert_results.get("report")
        if report_result and report_result.analysis and report_result.analysis.section_content:
            # 过滤元认知文本
            filtered_content = self._filter_meta_cognitive_text(
                report_result.analysis.section_content
            )
            content += filtered_content + "\n\n"
        elif pipeline_result.response:
            # 降级：使用完整响应
            filtered_content = self._filter_meta_cognitive_text(
                pipeline_result.response
            )
            content += filtered_content + "\n\n"
        else:
            content += "暂无综合分析内容。\n\n"

        # 插入企业分布地图
        try:
            from config.settings import settings
            amap_key = settings.amap_public_key or ""
            content = self._insert_enterprise_maps(
                content,
                visuals_by_expert,
                amap_key
            )
        except Exception as e:
            logger.warning("failed_to_insert_enterprise_maps", error=str(e))

        # 插入ECharts图表
        try:
            content = self._insert_echarts_charts(
                content,
                visuals_by_expert
            )
        except Exception as e:
            logger.warning("failed_to_insert_echarts_charts", error=str(e))

        # 添加元数据
        content += "---\n\n"
        content += f"**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
        content += f"**分析精度**: {pipeline_result.parsed_query.precision if pipeline_result.parsed_query else 'standard'}  \n"
        content += f"**参与专家**: {', '.join(pipeline_result.selected_experts)}  \n"
        content += f"**状态**: {pipeline_result.status}\n"

        return content

    def _generate_qmd_content(
        self,
        pipeline_result,
        processed_visuals: List[Dict[str, Any]],
        report_id: str
    ) -> str:
        """
        生成 qmd 报告内容

        Args:
            pipeline_result: Expert V3 执行结果
            processed_visuals: 处理后的图表列表
            report_id: 报告ID

        Returns:
            str: qmd 内容
        """
        # 提取信息
        parsed_query = pipeline_result.parsed_query
        location = parsed_query.location if parsed_query else "未知地点"
        date_str = datetime.now().strftime("%Y年%m月%d日")

        # 提取结论和建议
        conclusions = pipeline_result.conclusions or []
        recommendations = pipeline_result.recommendations or []

        # 按专家类型分组图表
        visuals_by_expert = {}
        for visual in processed_visuals:
            expert = visual.get("expert", "unknown")
            if expert not in visuals_by_expert:
                visuals_by_expert[expert] = []
            visuals_by_expert[expert].append(visual)

        # 构建 YAML front matter
        front_matter = f"""---
title: "{location}污染溯源分析报告"
date: "{datetime.now().isoformat()}"
format:
  html:
    toc: true
    number-sections: true
    code-fold: true
  docx:
    toc: true
    number-sections: true
  pptx:
    aspect-ratio: 16:9
---

"""

        # 构建标题和摘要
        content = f"""# {location}污染溯源分析报告

**报告生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**分析地点**: {location}
**分析精度**: {parsed_query.precision if parsed_query else 'standard'}
**参与专家**: {', '.join(pipeline_result.selected_experts)}

---

"""

        # 生成简化的综合分析章节
        content += self._generate_simplified_analysis(
            pipeline_result,
            visuals_by_expert
        )

        return front_matter + content

    def _generate_expert_sections(
        self,
        pipeline_result,
        visuals_by_expert: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        生成专家分析章节

        Args:
            pipeline_result: Expert V3 执行结果
            visuals_by_expert: 按专家分组的图表

        Returns:
            str: Markdown 内容
        """
        content = ""

        # 专家名称映射
        expert_names = {
            "weather": "气象条件分析",
            "component": "污染物组分分析",
            "viz": "数据可视化",
            "report": "综合分析"
        }

        # 遍历专家结果
        for expert_type, expert_result in pipeline_result.expert_results.items():
            expert_name = expert_names.get(expert_type, expert_type)

            # 跳过没有内容的专家章节（既无分析文字也无图表）
            has_summary = expert_result.analysis and expert_result.analysis.summary
            has_visuals = expert_type in visuals_by_expert and len(visuals_by_expert[expert_type]) > 0

            if not has_summary and not has_visuals:
                logger.info(
                    "skipping_empty_expert_section",
                    expert_type=expert_type,
                    expert_name=expert_name
                )
                continue

            content += f"## {expert_name}\n\n"

            # 添加专家总结
            if has_summary:
                content += f"{expert_result.analysis.summary}\n\n"

            # 添加图表
            if has_visuals:
                for visual in visuals_by_expert[expert_type]:
                    title = visual.get("title", "未命名图表")
                    content += f"### {title}\n\n"

                    # Check if this is a map visual
                    if visual.get("type") == "map" and visual.get("map_data"):
                        map_data = visual.get("map_data", {})
                        relative_path = visual.get("relative_path", "")

                        # Get AMap key
                        from config.settings import settings
                        amap_key = settings.amap_public_key or ""

                        if amap_key:
                            # Conditional rendering: interactive for HTML, static for DOCX/PPTX
                            map_html = self._generate_map_html_block(
                                visual.get("id", "map"),
                                map_data,
                                amap_key
                            )
                            content += '::: {.content-hidden when-format="docx"}\n\n'
                            content += '```{=html}\n'
                            content += map_html + '\n'
                            content += '```\n\n'
                            content += ':::\n\n'
                            content += '::: {.content-hidden when-format="html"}\n\n'
                            content += f"![]({relative_path})\n\n"
                            content += ':::\n\n'
                        else:
                            # No AMap key, fall back to static image only
                            content += f"![]({relative_path})\n\n"
                    else:
                        relative_path = visual.get("relative_path", "")
                        content += f"![{title}]({relative_path})\n\n"

            # 添加关键发现
            if expert_result.analysis and expert_result.analysis.key_findings:
                content += "#### 关键发现\n\n"
                for finding in expert_result.analysis.key_findings:
                    content += f"- {finding}\n"
                content += "\n"

        return content

    def _generate_final_conclusion(
        self,
        pipeline_result,
        conclusions: List[str],
        recommendations: List[str]
    ) -> str:
        """
        生成最终结论章节

        Args:
            pipeline_result: Expert V3 执行结果
            conclusions: 结论列表
            recommendations: 建议列表

        Returns:
            str: Markdown 内容
        """
        content = "## 综合分析结论\n\n"

        # 添加完整响应
        if pipeline_result.response:
            content += f"{pipeline_result.response}\n\n"

        # 添加元数据
        content += "---\n\n"
        content += f"**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
        content += f"**分析精度**: {pipeline_result.parsed_query.precision if pipeline_result.parsed_query else 'standard'}  \n"
        content += f"**参与专家**: {', '.join(pipeline_result.selected_experts)}  \n"
        content += f"**状态**: {pipeline_result.status}\n"

        return content

    def _save_metadata(
        self,
        report_dir: Path,
        pipeline_result,
        report_id: str
    ):
        """
        保存报告元数据

        Args:
            report_dir: 报告目录
            pipeline_result: Expert V3 执行结果
            report_id: 报告ID
        """
        meta = {
            "report_id": report_id,
            "report_type": "tracing_report",
            "created_at": datetime.now().isoformat(),
            "query": pipeline_result.query,
            "parsed_query": pipeline_result.parsed_query.dict() if pipeline_result.parsed_query else None,
            "selected_experts": pipeline_result.selected_experts,
            "status": pipeline_result.status,
            "confidence": pipeline_result.confidence,
            "conclusions": pipeline_result.conclusions,
            "recommendations": pipeline_result.recommendations,
            "data_ids": pipeline_result.data_ids,
            "visuals_count": len(pipeline_result.visuals),
            "expert_results": {
                k: {
                    "status": v.status,
                    "confidence": v.analysis.confidence if v.analysis else None,
                    "summary": v.analysis.summary if v.analysis else None
                }
                for k, v in pipeline_result.expert_results.items()
            }
        }

        meta_path = report_dir / "meta.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        logger.info("metadata_saved", path=str(meta_path))
