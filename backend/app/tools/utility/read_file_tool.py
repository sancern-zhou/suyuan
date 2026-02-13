"""
ReadFile 工具 - 读取文件内容（支持图片自动分析）

让 LLM 能够读取本地文件系统中的文件：
- 文本文件：直接返回内容
- 图片文件：自动调用 Vision API 进行内容分析（智能模式）

特性：
- 自动检测文件类型
- 图片文件自动分析（类似 Claude Code 的 Vision 能力）
- 可选关闭自动分析（auto_analyze=False）
- 支持多种分析类型（OCR、描述、图表分析等）
"""
import os
import base64
from pathlib import Path
from typing import Dict, Any, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()


class ReadFileTool(LLMTool):
    """
    文件读取工具（支持图片）

    功能：
    - 读取文本文件内容
    - 读取图片文件并转换为 base64
    - 自动检测文件类型
    """

    # 支持的图片格式
    IMAGE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'
    }

    def __init__(self):
        super().__init__(
            name="read_file",
            description="""读取文件内容（统一文件读取入口，自动识别类型）

特性：
- 文本文件：直接返回文本内容
- 图片文件：自动调用 Vision API 分析图片内容（可关闭）
- 目录列表：查看目录中的文件和子目录
- 自动检测文件类型并智能处理

使用场景：
- 读取文本文件（代码、配置、日志等）
- 读取并分析图片（图表、文档截图、照片等）
- 查看工作目录中的文件内容

示例：
- read_file(path="D:/work_dir/data.txt")       # 文本文件
- read_file(path="D:/work_dir/chart.png")      # 图片文件（自动分析）
- read_file(path="D:/work_dir")                # 查看目录内容
- read_file(path="D:/work_dir/doc.png", analysis_type="ocr")  # OCR识别
- read_file(path="D:/work_dir/photo.jpg", auto_analyze=False)  # 只读取不分析

参数说明：
- path: 文件或目录路径（必填）
- auto_analyze: 是否自动分析图片（默认 True）
- analysis_type: 图片分析类型（ocr/describe/chart/analyze，默认 analyze）
- encoding: 文本文件编码（默认 utf-8）

限制：
- 图片大小限制：5MB
- 工作目录限制：D:/溯源/ 及其子目录

注意：
- 图片文件会自动进行内容分析，分析结果以文本形式返回
- 不返回 base64 数据（避免 token 浪费）
- 如需手动控制图片分析，设置 auto_analyze=False
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        # 工作目录限制
        self.working_dir = Path(__file__).parent.parent.parent.parent.parent.parent  # D:\溯源\
        self.max_image_size = 5 * 1024 * 1024  # 5MB

    async def execute(
        self,
        path: str,
        encoding: str = "utf-8",
        auto_analyze: bool = True,
        analysis_type: str = "analyze",
        **kwargs
    ) -> Dict[str, Any]:
        """
        读取文件内容

        Args:
            path: 文件路径（绝对路径或相对路径）
            encoding: 文本文件编码（默认 utf-8）
            auto_analyze: 是否自动分析图片（默认 True）
            analysis_type: 图片分析类型（ocr/describe/chart/analyze，默认 analyze）

        Returns:
            {
                "status": "success|failed",
                "success": bool,
                "data": {
                    "type": "text|image",
                    "content": str,  # 文本内容或 base64
                    "format": str,  # 文件格式（txt, png等）
                    "size": int,    # 文件大小
                    "analysis": dict  # 图片分析结果（仅图片文件）
                },
                "metadata": {...},
                "summary": str
            }
        """
        try:
            # 1. 解析文件路径
            file_path = self._resolve_path(path)
            if not file_path:
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"文件路径无效或超出工作目录范围: {path}",
                    "summary": f"❌ 无法访问文件: {path}"
                }

            # 2. 检查文件是否存在
            if not file_path.exists():
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"文件不存在: {path}",
                    "summary": f"❌ 文件不存在: {path}"
                }

            # 2.5. 检查是否为目录
            if file_path.is_dir():
                # 列出目录内容
                try:
                    items = list(file_path.iterdir())
                    item_list = []
                    for item in sorted(items, key=lambda x: (not x.is_dir(), x.name)):
                        item_type = "DIR " if item.is_dir() else "FILE"
                        item_list.append(f"{item_type} {item.name}")

                    content = "\n".join(item_list) if item_list else "(空目录)"
                    return {
                        "status": "success",
                        "success": True,
                        "data": {
                            "type": "directory",
                            "content": content,
                            "path": str(file_path),
                            "item_count": len(items)
                        },
                        "metadata": {
                            "schema_version": "v2.0",
                            "generator": "read_file",
                            "file_type": "directory"
                        },
                        "summary": f"📁 目录内容: {file_path.name} ({len(items)} 项)"
                    }
                except Exception as e:
                    return {
                        "status": "failed",
                        "success": False,
                        "error": f"无法列出目录内容: {str(e)}",
                        "summary": f"❌ 无法访问目录: {file_path.name}"
                    }

            # 3. 获取文件信息
            file_size = file_path.stat().st_size
            file_ext = file_path.suffix.lower()

            # 4. 判断文件类型
            is_image = file_ext in self.IMAGE_EXTENSIONS

            if is_image:
                # 读取图片文件（可选自动分析）
                return await self._read_image(
                    file_path,
                    file_size,
                    auto_analyze=auto_analyze,
                    analysis_type=analysis_type
                )
            else:
                # 读取文本文件
                return await self._read_text(file_path, encoding, file_size)

        except Exception as e:
            logger.error("read_file_failed", path=path, error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "summary": f"❌ 读取文件失败: {str(e)[:50]}"
            }

    async def _read_image(
        self,
        file_path: Path,
        file_size: int,
        auto_analyze: bool = True,
        analysis_type: str = "analyze"
    ) -> Dict[str, Any]:
        """读取图片文件（自动分析，不返回 base64）

        优化说明：
        - base64 只在 analyze_image 内部使用（调用视觉模型 API）
        - 不返回 base64 给 LLM，避免 token 浪费
        - 只返回分析结果文本和图片元信息
        """
        try:
            # 检查文件大小
            if file_size > self.max_image_size:
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"图片文件过大: {file_size} bytes (最大 {self.max_image_size} bytes)",
                    "summary": f"❌ 图片过大，超过5MB限制"
                }

            # 获取图片格式
            file_ext = file_path.suffix[1:]  # 去掉点号

            # 构建基础结果（不包含 base64 content）
            result = {
                "status": "success",
                "success": True,
                "data": {
                    "type": "image",
                    "format": file_ext,
                    "size": file_size,
                    "path": str(file_path)
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "read_file",
                    "file_type": "image"
                }
            }

            # ✨ 自动分析图片（默认开启）
            if auto_analyze:
                logger.info("auto_analyzing_image", path=str(file_path), type=analysis_type)

                try:
                    # 导入 AnalyzeImage 工具（延迟导入避免循环依赖）
                    from app.tools.utility.analyze_image_tool import AnalyzeImageTool

                    # 创建分析工具实例
                    analyze_tool = AnalyzeImageTool()

                    # 调用分析工具（analyze_image 内部会自己读取文件并转换为 base64）
                    analyze_result = await analyze_tool.execute(
                        path=str(file_path),
                        operation=analysis_type
                    )

                    if analyze_result.get('success'):
                        # 将分析结果添加到数据中
                        result['data']['analysis'] = analyze_result['data']['analysis']
                        result['data']['operation'] = analyze_result['data']['operation']

                        # 更新摘要信息
                        summary = f"✅ 读取并分析图片成功: {file_path.name} ({file_size} bytes, {file_ext})"
                        if analysis_type != "analyze":
                            summary += f" [{analysis_type}]"
                        result['summary'] = summary

                        logger.info("auto_analyze_success", path=str(file_path))
                    else:
                        # 分析失败
                        result['data']['analysis_error'] = analyze_result.get('error', '分析失败')
                        result['summary'] = f"✅ 读取图片成功（分析失败）: {file_path.name}"
                        logger.warning("auto_analyze_failed", path=str(file_path), error=analyze_result.get('error'))

                except ImportError:
                    # AnalyzeImage 工具不可用
                    result['data']['analysis_error'] = "AnalyzeImage 工具不可用"
                    result['summary'] = f"✅ 读取图片成功（分析工具不可用）: {file_path.name}"
                    logger.warning("analyze_image_unavailable", path=str(file_path))

                except Exception as e:
                    # 分析过程出错
                    result['data']['analysis_error'] = str(e)
                    result['summary'] = f"✅ 读取图片成功（分析出错）: {file_path.name}"
                    logger.error("auto_analyze_error", path=str(file_path), error=str(e))
            else:
                # 不自动分析（只返回图片信息）
                result['summary'] = f"✅ 读取图片信息: {file_path.name} ({file_size} bytes, {file_ext})"

            return result

        except Exception as e:
            logger.error("read_image_failed", path=str(file_path), error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "summary": f"❌ 读取图片失败: {str(e)[:50]}"
            }

    async def _read_text(
        self,
        file_path: Path,
        encoding: str,
        file_size: int
    ) -> Dict[str, Any]:
        """读取文本文件（返回完整内容）"""
        try:
            # 读取文本内容（完全不截断，依赖上下文压缩策略）
            content = file_path.read_text(encoding=encoding)

            return {
                "status": "success",
                "success": True,
                "data": {
                    "type": "text",
                    "format": file_path.suffix[1:] if file_path.suffix else "txt",
                    "content": content,  # 完整内容，不截断
                    "size": file_size,
                    "path": str(file_path)
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "read_file",
                    "file_type": "text",
                    "encoding": encoding
                },
                "summary": f"✅ 读取文件成功: {file_path.name} ({file_size} bytes)"
            }

        except UnicodeDecodeError:
            return {
                "status": "failed",
                "success": False,
                "error": f"编码错误（尝试使用 encoding='gbk' 或 encoding='latin-1'）",
                "summary": f"❌ 文本编码错误: {file_path.name}"
            }
        except Exception as e:
            logger.error("read_text_failed", path=str(file_path), error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "summary": f"❌ 读取文件失败: {str(e)[:50]}"
            }

    def _resolve_path(self, path: str) -> Optional[Path]:
        """
        解析文件路径，确保在工作目录范围内

        Args:
            path: 文件路径（绝对或相对）

        Returns:
            Path 对象或 None（如果路径无效）
        """
        try:
            # 转换为 Path 对象
            file_path = Path(path)

            # 如果是相对路径，基于工作目录解析
            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            # 解析为绝对路径
            file_path = file_path.resolve()

            # 检查是否在工作目录范围内
            if not file_path.is_relative_to(self.working_dir):
                logger.warning(
                    "path_escape_attempt",
                    requested_path=path,
                    allowed_dir=str(self.working_dir)
                )
                return None

            return file_path

        except Exception as e:
            logger.error("path_resolution_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "read_file",
            "description": """读取文件内容（统一文件读取入口，自动识别类型）

特性：
- 文本文件：返回文本内容
- 图片文件：自动调用 Vision API 分析图片内容（可关闭）
- 目录列表：查看目录中的文件和子目录
- 自动检测文件类型并智能处理

使用场景：
- 读取文本文件（代码、配置、日志等）
- 读取并分析图片（图表、文档截图、照片等）
- 查看工作目录中的文件内容

图片处理：
- 图片文件会自动进行内容分析，分析结果以文本形式返回
- 支持多种分析类型：OCR、描述、图表分析等
- 可通过 auto_analyze=False 关闭自动分析
- 不返回 base64 数据（避免 token 浪费）

示例：
- read_file(path="D:/work_dir/data.txt")  # 读取文本
- read_file(path="D:/work_dir/chart.png")  # 读取并自动分析图片
- read_file(path="D:/work_dir")  # 查看目录内容
- read_file(path="D:/work_dir/doc.png", analysis_type="ocr")  # OCR文字识别
- read_file(path="D:/work_dir/photo.jpg", auto_analyze=False)  # 只读取不分析

限制：
- 图片大小限制：5MB
- 工作目录限制：D:/溯源/ 及其子目录
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（绝对路径或相对路径）。示例：'D:/work_dir/data.txt' 或 'data/chart.png'"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "文本文件编码（默认 utf-8），对于中文文件可尝试 'gbk'",
                        "default": "utf-8"
                    },
                    "auto_analyze": {
                        "type": "boolean",
                        "description": "是否自动分析图片（默认 True）。设置为 False 则只读取图片数据，不调用 Vision API",
                        "default": True
                    },
                    "analysis_type": {
                        "type": "string",
                        "enum": ["ocr", "describe", "chart", "analyze"],
                        "description": "图片分析类型（仅当 auto_analyze=True 时有效）：ocr=文字识别, describe=图片描述, chart=图表分析, analyze=综合分析（默认）",
                        "default": "analyze"
                    }
                },
                "required": ["path"]
            }
        }

    def is_available(self) -> bool:
        """检查工具是否可用"""
        return True


# 创建工具实例
tool = ReadFileTool()
