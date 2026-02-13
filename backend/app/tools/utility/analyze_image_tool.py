"""
AnalyzeImage 工具 - 使用通义千问 VL 模型分析图片

调用通义千问 VL（Vision-Language）模型进行图片理解：
- OCR 文字识别
- 图片描述生成
- 数据图表提取
- 场景理解

配置说明：使用项目中已配置的通义千问 VL API
"""
import httpx
import base64
from pathlib import Path
from typing import Dict, Any, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()


class AnalyzeImageTool(LLMTool):
    """
    图片分析工具（通义千问 VL 模型）

    功能：
    - OCR 文字识别
    - 图片描述生成
    - 数据图表提取
    - 场景理解

    配置：使用项目中已配置的通义千问 VL API
    """

    # 通义千问VL API配置（与天气形势图工具保持一致）
    QWEN_VL_API_KEY = "sk-6b11fe1b4ed64504990e8ace35f976fb"
    QWEN_VL_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_VL_MODEL = "qwen-vl-max-latest"

    def __init__(self):
        super().__init__(
            name="analyze_image",
            description="""分析图片内容（使用通义千问 VL 模型）

使用场景：
- OCR 文字识别：提取图片中的文字
- 图片描述：生成图片的详细描述
- 图表分析：提取数据图表中的信息
- 场景理解：理解图片中的场景和对象

操作类型：
- ocr: 文字识别（提取图片中的所有文字）
- describe: 图片描述（详细描述图片内容）
- chart: 图表分析（提取图表中的数据和趋势）
- analyze: 综合分析（默认，包含以上所有内容）

示例：
- analyze_image(path="D:/work_dir/chart.png", operation="ocr")  # OCR识别
- analyze_image(path="D:/work_dir/photo.jpg", operation="describe")  # 图片描述
- analyze_image(path="D:/work_dir/plot.png", operation="chart", prompt="提取图表中的数据和趋势")  # 图表分析

配置：
- 使用通义千问 VL 模型（qwen-vl-max-latest）
- 支持的格式：PNG、JPG、JPEG、GIF、BMP、WEBP
- 图片大小限制：5MB
- 超时时间：120秒
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        # 工作目录限制
        self.working_dir = Path(__file__).parent.parent.parent.parent.parent.parent
        self.max_image_size = 5 * 1024 * 1024  # 5MB

    async def execute(
        self,
        path: str,
        operation: str = "analyze",
        prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        分析图片内容

        Args:
            path: 图片文件路径
            operation: 操作类型（ocr/describe/chart/analyze）
            prompt: 自定义分析提示词（可选）

        Returns:
            {
                "status": "success|failed",
                "success": bool,
                "data": {
                    "operation": str,
                    "analysis": str,  # 分析结果
                    "image_info": {...}
                },
                "metadata": {...},
                "summary": str
            }
        """
        try:
            # 1. 读取图片文件
            file_path = self._resolve_path(path)
            if not file_path or not file_path.exists():
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"图片文件不存在: {path}",
                    "summary": f"❌ 文件不存在: {path}"
                }

            # 2. 检查文件大小
            file_size = file_path.stat().st_size
            if file_size > self.max_image_size:
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"图片文件过大: {file_size} bytes",
                    "summary": f"❌ 图片过大，超过5MB限制"
                }

            # 3. 读取图片并转换为 base64
            with open(file_path, 'rb') as f:
                image_bytes = f.read()
                base64_data = base64.b64encode(image_bytes).decode('utf-8')

            file_ext = file_path.suffix[1:]  # 去掉点号

            # 4. 构造分析提示词
            if not prompt:
                prompt = self._get_default_prompt(operation)

            # 5. 调用 Vision API（使用已有的 MCP 工具）
            analysis_result = await self._call_vision_api(
                base64_data=base64_data,
                file_format=file_ext,
                prompt=prompt
            )

            return {
                "status": "success",
                "success": True,
                "data": {
                    "operation": operation,
                    "analysis": analysis_result,
                    "image_info": {
                        "path": str(file_path),
                        "format": file_ext,
                        "size": file_size
                    }
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "analyze_image",
                    "operation": operation
                },
                "summary": f"✅ 图片分析完成: {file_path.name} ({operation})"
            }

        except Exception as e:
            logger.error("analyze_image_failed", path=path, error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "summary": f"❌ 图片分析失败: {str(e)[:50]}"
            }

    def _get_default_prompt(self, operation: str) -> str:
        """获取默认的分析提示词"""
        prompts = {
            "ocr": "请提取图片中的所有文字内容，保持原有的格式和布局。如果是表格，请用Markdown表格格式输出。",
            "describe": "请详细描述这张图片的内容，包括主要对象、场景、颜色、布局等。",
            "chart": "请分析这张图表，提取其中的数据、趋势、坐标轴信息、图例说明等。",
            "analyze": "请全面分析这张图片，包括文字内容、主要对象、场景描述、数据信息等。"
        }
        return prompts.get(operation, prompts["analyze"])

    async def _call_vision_api(
        self,
        base64_data: str,
        file_format: str,
        prompt: str
    ) -> str:
        """
        调用通义千问 VL API 分析图片

        Args:
            base64_data: 图片 base64 数据
            file_format: 图片格式（png, jpg等）
            prompt: 分析提示词

        Returns:
            分析结果文本
        """
        try:
            # 构造 data URL
            data_url = f"data:image/{file_format};base64,{base64_data}"

            # 调用通义千问 VL API
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
                                        "image_url": {"url": data_url}
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt
                                    }
                                ]
                            }
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3
                    }
                )

                response.raise_for_status()
                result = response.json()
                analysis = result["choices"][0]["message"]["content"]

                logger.info(
                    "qwen_vl_analysis_success",
                    model=self.QWEN_VL_MODEL,
                    analysis_length=len(analysis)
                )

                return analysis

        except httpx.TimeoutException:
            logger.error("qwen_vl_timeout")
            return "图片分析超时（120秒）"
        except httpx.HTTPStatusError as e:
            logger.error(
                "qwen_vl_http_error",
                status=e.response.status_code,
                error=e.response.text[:500] if e.response else "No response"
            )
            return f"图片分析失败: HTTP {e.response.status_code}"
        except Exception as e:
            logger.error("qwen_vl_analysis_failed", error=str(e))
            return f"图片分析失败: {str(e)[:100]}"

    def _resolve_path(self, path: str) -> Optional[Path]:
        """解析文件路径（与 ReadFile 工具相同）"""
        try:
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = self.working_dir / file_path
            file_path = file_path.resolve()

            if not file_path.is_relative_to(self.working_dir):
                return None

            return file_path
        except Exception:
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "analyze_image",
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "图片文件路径（绝对路径或相对路径）"
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["ocr", "describe", "chart", "analyze"],
                        "description": "操作类型：ocr=文字识别, describe=图片描述, chart=图表分析, analyze=综合分析（默认）"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "自定义分析提示词（可选，不指定则使用默认提示词）"
                    }
                },
                "required": ["path"]
            }
        }

    def is_available(self) -> bool:
        """检查工具是否可用"""
        return True


# 创建工具实例
tool = AnalyzeImageTool()
