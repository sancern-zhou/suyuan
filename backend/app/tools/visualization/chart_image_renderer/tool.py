"""
Chart Image Renderer Tool - ECharts图表图片渲染工具

将ECharts JSON配置通过Playwright无头浏览器渲染为PNG图片。
用于社交模式（微信/QQ等）发送图表图片。
"""

import json
import os
import uuid
import asyncio
from typing import Any, Dict, Optional
from pathlib import Path

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()

# 模板文件路径
TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_HTML = TEMPLATE_DIR / "template.html"

# 输出目录
# ✅ 使用统一路径配置
from app.utils.path_config import get_chart_images_dir
OUTPUT_DIR = get_chart_images_dir()


class ChartImageRenderer(LLMTool):
    """
    ECharts图表图片渲染工具
    
    将ECharts JSON配置渲染为PNG图片，用于社交模式发送。
    
    使用场景：
    - 微信/QQ等社交渠道需要发送图表图片
    - 将ECharts配置转换为静态图片
    
    输入：
    - echarts_option: 完整的ECharts配置对象（dict）
    - width: 图片宽度（默认800）
    - height: 图片高度（默认500）
    
    输出：
    - image_path: 生成的PNG图片路径
    - image_url: 图片的访问URL（如果有）
    """
    
    def __init__(self):
        function_schema = {
            "name": "render_chart_to_image",
            "description": "将ECharts配置渲染为PNG图片，用于社交模式发送图表",
            "parameters": {
                "type": "object",
                "properties": {
                    "echarts_option": {
                        "type": "object",
                        "description": "完整的ECharts配置对象，包含xAxis、yAxis、series等"
                    },
                    "chart_data_id": {
                        "type": "string",
                        "description": "图表数据的data_id（从context中获取），与echarts_option二选一"
                    },
                    "width": {
                        "type": "integer",
                        "description": "图片宽度（像素），默认800",
                        "default": 800
                    },
                    "height": {
                        "type": "integer",
                        "description": "图片高度（像素），默认500",
                        "default": 500
                    }
                },
                "required": []
            }
        }
        
        super().__init__(
            name="render_chart_to_image",
            description="将ECharts配置渲染为PNG图片，用于社交模式发送图表",
            category=ToolCategory.VISUALIZATION,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )
    
    async def execute(
        self,
        context: Any,
        echarts_option: Optional[Dict[str, Any]] = None,
        chart_data_id: Optional[str] = None,
        width: int = 800,
        height: int = 500,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行图表渲染
        
        Args:
            context: 执行上下文
            echarts_option: ECharts配置对象
            chart_data_id: 图表数据ID（从context获取）
            width: 图片宽度
            height: 图片高度
            
        Returns:
            包含image_path的结果字典
        """
        try:
            # Step 1: 获取ECharts配置
            if echarts_option is None and chart_data_id is not None:
                # 从context加载
                try:
                    chart_data = context.get_raw_data(chart_data_id)
                    if isinstance(chart_data, list) and len(chart_data) > 0:
                        first_item = chart_data[0]
                        # 尝试从payload或config获取
                        if isinstance(first_item, dict):
                            if "payload" in first_item:
                                echarts_option = first_item["payload"].get("data", first_item["payload"])
                            elif "config" in first_item:
                                echarts_option = first_item["config"]
                            elif "data" in first_item:
                                echarts_option = first_item
                            else:
                                echarts_option = first_item
                except Exception as e:
                    logger.error("chart_data_load_failed", chart_data_id=chart_data_id, error=str(e))
                    return {
                        "status": "failed",
                        "success": False,
                        "data": None,
                        "metadata": {"tool_name": "render_chart_to_image", "error_type": "data_load_failed"},
                        "summary": f"[FAIL] 无法加载图表数据: {str(e)}"
                    }
            
            if echarts_option is None:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {"tool_name": "render_chart_to_image", "error_type": "no_input"},
                    "summary": "[FAIL] 未提供ECharts配置或chart_data_id"
                }
            
            # Step 2: 确保输出目录存在
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            
            # Step 3: 生成输出文件名
            image_filename = f"chart_{uuid.uuid4().hex[:12]}.png"
            image_path = OUTPUT_DIR / image_filename

            # Step 3.5: 验证 ECharts 配置有效性
            validation_result = self._validate_echarts_option(echarts_option)
            if not validation_result["valid"]:
                logger.error(
                    "echarts_option_invalid",
                    validation_errors=validation_result["errors"],
                    echarts_keys=list(echarts_option.keys())
                )
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "render_chart_to_image",
                        "error_type": "invalid_option",
                        "validation_errors": validation_result["errors"]
                    },
                    "summary": f"[FAIL] ECharts配置无效: {', '.join(validation_result['errors'])}"
                }

            # Step 4: 使用Playwright渲染
            logger.info(
                "chart_render_start",
                width=width,
                height=height,
                output_path=str(image_path)
            )
            
            success = await self._render_with_playwright(
                echarts_option=echarts_option,
                output_path=str(image_path),
                width=width,
                height=height
            )
            
            if not success or not image_path.exists():
                logger.error(
                    "chart_render_failed_final",
                    success=success,
                    image_exists=image_path.exists() if image_path else False,
                    image_path=str(image_path) if image_path else None,
                    echarts_option_keys=list(echarts_option.keys()) if echarts_option else []
                )
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "render_chart_to_image",
                        "error_type": "render_failed",
                        "echarts_keys": list(echarts_option.keys()) if echarts_option else []
                    },
                    "summary": "[FAIL] 图表渲染失败"
                }
            
            # Step 5: 返回结果
            file_size = image_path.stat().st_size
            logger.info(
                "chart_render_success",
                image_path=str(image_path),
                file_size=file_size
            )
            
            return {
                "status": "success",
                "success": True,
                "data": {
                    "image_path": str(image_path),
                    "image_filename": image_filename,
                    "width": width,
                    "height": height,
                    "file_size": file_size
                },
                "metadata": {
                    "tool_name": "render_chart_to_image",
                    "image_path": str(image_path)
                },
                "summary": f"[OK] 图表渲染完成，图片路径: {image_path}"
            }
            
        except Exception as e:
            logger.error("chart_render_failed", error=str(e), exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "render_chart_to_image", "error_type": "execution_failed"},
                "summary": f"[FAIL] 图表渲染失败: {str(e)}"
            }

    def _validate_echarts_option(self, option: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证 ECharts 配置的有效性

        Args:
            option: ECharts 配置字典

        Returns:
            验证结果：{"valid": bool, "errors": List[str]}
        """
        errors = []

        # 检查必需字段
        if not option.get("series"):
            errors.append("缺少 series 配置")
        elif not isinstance(option["series"], list):
            errors.append("series 必须是数组")
        elif len(option["series"]) == 0:
            errors.append("series 数组为空")

        # 检查 xAxis（如果有 series，必须有 xAxis）
        if option.get("series") and not option.get("xAxis"):
            errors.append("缺少 xAxis 配置")

        # 检查 xAxis 数据
        if option.get("xAxis"):
            xaxis = option["xAxis"]
            if isinstance(xaxis, dict):
                xdata = xaxis.get("data", [])
                if not xdata or not isinstance(xdata, list) or len(xdata) == 0:
                    errors.append("xAxis.data 为空或无效")

        # 检查 yAxis
        if option.get("series") and not option.get("yAxis"):
            errors.append("缺少 yAxis 配置")

        # 检查 yAxis 配置
        if option.get("yAxis"):
            yaxis = option["yAxis"]
            # yAxis 可以是数组（双Y轴）或对象（单Y轴）
            if isinstance(yaxis, list):
                if len(yaxis) == 0:
                    errors.append("yAxis 数组为空")
            elif not isinstance(yaxis, dict):
                errors.append("yAxis 必须是对象或数组")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

    async def _render_with_playwright(
        self,
        echarts_option: Dict[str, Any],
        output_path: str,
        width: int,
        height: int
    ) -> bool:
        """
        使用Playwright渲染ECharts为PNG
        
        Args:
            echarts_option: ECharts配置
            output_path: 输出路径
            width: 图片宽度
            height: 图片高度
            
        Returns:
            是否成功
        """
        try:
            from playwright.async_api import async_playwright
            
            # 读取HTML模板
            template_content = TEMPLATE_HTML.read_text(encoding="utf-8")
            
            # 将ECharts配置转为JSON字符串
            echarts_json = json.dumps(echarts_option, ensure_ascii=False)
            
            async with async_playwright() as p:
                # 启动无头浏览器
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                
                # 创建页面
                page = await browser.new_page(
                    viewport={"width": width + 20, "height": height + 20}
                )
                
                # 加载HTML模板
                await page.set_content(template_content, wait_until="networkidle")
                
                # 注入ECharts配置
                await page.evaluate(f"window.__ECHARTS_OPTION__ = {echarts_json};")
                
                # 触发图表初始化
                await page.evaluate("""
                    if (typeof initChart === 'function') {
                        initChart();
                    }
                """)
                
                # 等待图表渲染完成
                await page.wait_for_function(
                    "window.__CHART_RENDERED__ === true",
                    timeout=10000
                )
                
                # 额外等待确保动画完成
                await asyncio.sleep(0.5)
                
                # 截图
                chart_element = page.locator('#chart-container')
                await chart_element.screenshot(path=output_path, type="png")
                
                # 关闭浏览器
                await browser.close()
            
            return True
            
        except ImportError:
            logger.error("playwright_not_installed", error="playwright package not found")
            return False
        except Exception as e:
            logger.error(
                "playwright_render_failed",
                error=str(e),
                error_type=type(e).__name__,
                echarts_option_keys=list(echarts_option.keys()) if echarts_option else [],
                has_xaxis="xAxis" in echarts_option if echarts_option else False,
                has_yaxis="yAxis" in echarts_option if echarts_option else False,
                has_series="series" in echarts_option if echarts_option else False,
                series_count=len(echarts_option.get("series", [])) if echarts_option else 0,
                exc_info=True
            )
            return False


def render_chart_to_image_sync(echarts_option: Dict[str, Any], width: int = 800, height: int = 500) -> Optional[str]:
    """
    同步版本的图表渲染（便捷函数）
    
    Args:
        echarts_option: ECharts配置
        width: 图片宽度
        height: 图片高度
        
    Returns:
        图片路径，失败返回None
    """
    renderer = ChartImageRenderer()
    
    # 创建简单的context
    class SimpleContext:
        pass
    
    context = SimpleContext()
    
    # 运行异步函数
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            renderer.execute(
                context=context,
                echarts_option=echarts_option,
                width=width,
                height=height
            )
        )
        if result.get("success"):
            return result["data"]["image_path"]
        return None
    finally:
        loop.close()
