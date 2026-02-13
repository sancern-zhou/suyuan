"""
Get Weather Situation Map Tool

LLM可调用的天气形势图解读工具

功能：
- 获取中央气象台天气形势图
- 使用通义千问VL模型进行图片解读
- 返回当前气象形势分析结果和图片URL
"""
from typing import Dict, Any, Optional
from datetime import datetime
import structlog
import httpx

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


class GetWeatherSituationMapTool(LLMTool):
    """
    天气形势图解读工具

    获取中央气象台天气形势图并使用AI进行专业解读
    """

    # 通义千问VL API配置（硬编码）
    QWEN_VL_API_KEY = "sk-6b11fe1b4ed64504990e8ace35f976fb"
    QWEN_VL_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_VL_MODEL = "qwen-vl-max-latest"

    # 天气形势图URL模板
    WEATHER_MAP_BASE_URL = "http://data.suncereltd.cn:8313/1001"
    WEATHER_MAP_SUFFIX = "--%2B00%2B--%2B--%2B--%2B00%2B--.png"

    def __init__(self):
        function_schema = {
            "name": "get_weather_situation_map",
            "description": """获取中央气象台天气形势图并进行AI解读。

适用场景：
- 污染溯源分析中需要了解当前天气形势
- 分析大尺度天气系统对区域污染的影响
- 识别高压、低压、冷锋、暖锋等天气系统

返回：
- 天气形势图URL（可直接访问）
- AI解读的天气系统分析
- 对污染扩散的影响评估
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "日期，格式YYYYMMDD，如20260204。默认为当天日期。"
                    },
                    "analysis_focus": {
                        "type": "string",
                        "description": "分析重点（可选），如'高压系统'、'冷空气'、'污染扩散条件'等。默认为全面分析。",
                        "default": "全面分析"
                    }
                },
                "required": []
            }
        }

        super().__init__(
            name="get_weather_situation_map",
            description="Get weather situation map from CMA and analyze with AI (VL model)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

    async def execute(
        self,
        date: Optional[str] = None,
        analysis_focus: str = "全面分析",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行天气形势图解读

        Args:
            date: 日期，格式YYYYMMDD。如果为None，使用当天日期
            analysis_focus: 分析重点

        Returns:
            Dict: 解读结果，包含：
                - image_url: 天气形势图URL
                - analysis: AI解读结果
                - date: 日期
        """
        try:
            # 1. 处理日期参数
            if not date:
                date = datetime.now().strftime("%Y%m%d")

            # 验证日期格式
            try:
                date_obj = datetime.strptime(date, "%Y%m%d")
            except ValueError:
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"日期格式错误，应为YYYYMMDD格式，当前值: {date}",
                    "data": None,
                    "metadata": {
                        "schema_version": "v2.0",
                        "generator": "get_weather_situation_map"
                    },
                    "summary": "日期格式错误"
                }

            # 检查是否为未来日期
            if date_obj > datetime.now():
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"不支持未来日期: {date}",
                    "data": None,
                    "metadata": {
                        "schema_version": "v2.0",
                        "generator": "get_weather_situation_map"
                    },
                    "summary": "不支持未来日期"
                }

            logger.info(
                "weather_situation_map_query_started",
                date=date,
                analysis_focus=analysis_focus
            )

            # 2. 构造图片URL
            image_url = f"{self.WEATHER_MAP_BASE_URL}/{date}/{self.WEATHER_MAP_SUFFIX}"

            # 3. 验证图片是否存在
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    head_response = await client.head(image_url)
                    if head_response.status_code != 200:
                        logger.warning(
                            "weather_map_not_found",
                            date=date,
                            status_code=head_response.status_code,
                            url=image_url
                        )
                        return {
                            "status": "failed",
                            "success": False,
                            "error": f"天气形势图不存在（日期: {date}），可能该日期数据尚未发布",
                            "data": None,
                            "metadata": {
                                "schema_version": "v2.0",
                                "generator": "get_weather_situation_map",
                                "image_url": image_url
                            },
                            "summary": f"{date}天气形势图不存在"
                        }
            except Exception as e:
                logger.warning("weather_map_validation_failed", date=date, error=str(e))
                # 验证失败不阻断流程，继续尝试解读

            # 4. 调用通义千问VL模型解读图片
            analysis_result = await self._analyze_weather_map(
                image_url=image_url,
                date=date,
                analysis_focus=analysis_focus
            )

            if not analysis_result["success"]:
                return {
                    "status": "failed",
                    "success": False,
                    "error": analysis_result.get("error", "AI解读失败"),
                    "data": {
                        "date": date,
                        "image_url": image_url
                    },
                    "metadata": {
                        "schema_version": "v2.0",
                        "generator": "get_weather_situation_map",
                        "model": self.QWEN_VL_MODEL,
                        "image_source": "中央气象台"
                    },
                    "summary": f"{date}天气形势图AI解读失败"
                }

            # 5. 构造返回结果
            logger.info(
                "weather_situation_map_analysis_success",
                date=date,
                analysis_length=len(analysis_result["analysis"])
            )

            return {
                "status": "success",
                "success": True,
                "data": {
                    "date": date,
                    "date_formatted": date_obj.strftime("%Y年%m月%d日"),
                    "image_url": image_url,
                    "analysis": analysis_result["analysis"],
                    "analysis_focus": analysis_focus
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "get_weather_situation_map",
                    "generator_version": "1.0.0",
                    "model": self.QWEN_VL_MODEL,
                    "image_source": "中央气象台",
                    "field_mapping_applied": False,
                    "record_count": 1
                },
                "summary": f"{date_obj.strftime('%Y年%m月%d日')}天气形势图解读完成"
            }

        except Exception as e:
            logger.error(
                "weather_situation_map_query_failed",
                date=date,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "data": None,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "get_weather_situation_map"
                },
                "summary": f"天气形势图查询失败: {str(e)[:50]}"
            }

    async def _analyze_weather_map(
        self,
        image_url: str,
        date: str,
        analysis_focus: str
    ) -> Dict[str, Any]:
        """
        使用通义千问VL模型解读天气形势图

        Args:
            image_url: 天气形势图URL
            date: 日期
            analysis_focus: 分析重点

        Returns:
            Dict: {"success": bool, "analysis": str, "error": str}
        """
        try:
            # 构造分析Prompt
            date_obj = datetime.strptime(date, "%Y%m%d")
            date_formatted = date_obj.strftime("%Y年%m月%d日")

            prompt = f"""请详细解读这张{date_formatted}的天气形势图，重点分析以下内容：

1. **天气系统识别**：识别图中的主要天气系统（高压、低压、冷锋、暖锋、槽脊等）
2. **系统位置与强度**：描述各系统的地理位置、中心位置和强度特征
3. **天气影响**：分析这些系统对中国各地区（特别是华北、华东地区）天气的影响
4. **污染扩散条件**：评估当前天气形势对大气污染扩散的影响（风场、气压场特征）

{f'特别关注: {analysis_focus}' if analysis_focus != '全面分析' else ''}

请用专业但易懂的语言进行分析，输出内容精练简洁，不要太长，重点关注当前气象形势，不需要预测未来趋势。
"""

            # 调用通义千问VL API
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.QWEN_VL_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.QWEN_VL_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.QWEN_VL_MODEL,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": image_url}
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt
                                    }
                                ]
                            }
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3  # 较低温度，确保分析准确性
                    }
                )

                response.raise_for_status()
                result = response.json()

                analysis = result["choices"][0]["message"]["content"]

                logger.info(
                    "qwen_vl_analysis_success",
                    date=date,
                    analysis_length=len(analysis)
                )

                return {
                    "success": True,
                    "analysis": analysis.strip(),
                    "error": None
                }

        except httpx.TimeoutException as e:
            logger.error("qwen_vl_timeout", date=date, error=str(e))
            return {
                "success": False,
                "analysis": None,
                "error": "AI解读超时（120秒）"
            }
        except httpx.HTTPStatusError as e:
            error_body = e.response.text if e.response else "No response body"
            logger.error(
                "qwen_vl_http_error",
                date=date,
                status=e.response.status_code,
                error_body=error_body[:500]
            )
            return {
                "success": False,
                "analysis": None,
                "error": f"AI解读失败: HTTP {e.response.status_code}"
            }
        except Exception as e:
            logger.error(
                "qwen_vl_analysis_failed",
                date=date,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "analysis": None,
                "error": f"AI解读异常: {str(e)[:100]}"
            }
