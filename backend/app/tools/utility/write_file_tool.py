"""
WriteFile 工具 - 创建或覆写文件

功能：
- 创建新文件或覆写已有文件
- 自动创建父目录（如不存在）
- 支持多种编码（utf-8/gbk等）
- 工作目录安全限制
- 文件大小限制（防止误写超大文件）

使用场景：
- 创建新的配置文件
- 生成代码文件
- 导出数据到文本文件
- 创建文档、日志等
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()

# 文件大小限制（10MB）
MAX_FILE_SIZE = 10 * 1024 * 1024


class WriteFileTool(LLMTool):
    """
    文件写入工具

    功能：
    - 创建新文件或覆写已有文件
    - 自动创建父目录
    - 支持多种编码
    - 安全检查（路径限制、大小限制）
    """

    def __init__(self):
        super().__init__(
            name="write_file",
            description="""创建或覆写文件内容

功能：
- 创建新文件或完全覆写已有文件的内容
- 自动创建父目录（如不存在）
- 支持多种文本编码（utf-8/gbk等）

使用场景：
- 创建新的配置文件（config.json, settings.yaml）
- 生成代码文件（script.py, module.js）
- 导出数据到文本文件（report.txt, data.csv）
- 创建文档（README.md, notes.txt）

示例：
- write_file(path="D:/work/config.json", content='{"port": 8000}')
- write_file(path="D:/work/script.py", content="def main():\\n    print('hello')")
- write_file(path="D:/work/data.txt", content="line1\\nline2\\nline3")

参数说明：
- path: 文件路径（必填，绝对路径或相对路径）
- content: 文件内容（必填）
- encoding: 文件编码（默认 utf-8）
- create_dirs: 是否自动创建父目录（默认 True）

注意：
- 如果文件已存在，会完全覆写（不是追加）
- 工作目录限制：D:/溯源/ 及其子目录
- 文件大小限制：最大 10MB
- 二进制文件请使用其他工具
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        self.working_dir = Path.cwd().parent  # D:\溯源\ 或 /opt/app/ 等

    async def execute(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        写入文件内容

        Args:
            path: 文件路径
            content: 文件内容
            encoding: 文件编码（默认 utf-8）
            create_dirs: 是否自动创建父目录（默认 True）

        Returns:
            {
                "success": bool,
                "data": {
                    "path": str,
                    "size": int,           # 文件大小（字节）
                    "lines": int,          # 行数
                    "encoding": str,
                    "created": bool,       # 是否新建（False表示覆写）
                },
                "summary": str
            }
        """
        try:
            # 1. 路径安全检查
            resolved_path = self._resolve_path(path)
            if not resolved_path:
                return {
                    "success": False,
                    "error": f"文件路径无效或超出工作目录范围: {path}",
                    "summary": f"写入失败：路径不合法"
                }

            # 2. 检查是否为目录
            if resolved_path.exists() and resolved_path.is_dir():
                return {
                    "success": False,
                    "error": f"路径是目录而非文件: {path}",
                    "summary": f"写入失败：路径是目录"
                }

            # 3. 文件大小检查
            content_size = len(content.encode(encoding))
            if content_size > MAX_FILE_SIZE:
                return {
                    "success": False,
                    "error": f"文件内容过大（{content_size / 1024 / 1024:.2f}MB），超过限制（{MAX_FILE_SIZE / 1024 / 1024}MB）",
                    "summary": f"写入失败：内容过大"
                }

            # 4. 记录是否为新建文件
            is_new_file = not resolved_path.exists()

            # 5. 创建父目录（如需要）
            if create_dirs and not resolved_path.parent.exists():
                try:
                    resolved_path.parent.mkdir(parents=True, exist_ok=True)
                    logger.info("write_file_dirs_created", path=str(resolved_path.parent))
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"创建父目录失败: {str(e)}",
                        "summary": f"写入失败：无法创建目录"
                    }

            # 6. 写入文件
            try:
                resolved_path.write_text(content, encoding=encoding)
            except UnicodeEncodeError:
                return {
                    "success": False,
                    "error": f"编码错误，内容无法用 {encoding} 编码，请尝试 encoding='utf-8'",
                    "summary": f"写入失败：编码错误"
                }

            # 7. 统计信息
            file_size = resolved_path.stat().st_size
            line_count = content.count('\n') + (1 if content and not content.endswith('\n') else 0)

            logger.info(
                "write_file_success",
                file=str(resolved_path),
                size=file_size,
                lines=line_count,
                created=is_new_file
            )

            return {
                "success": True,
                "data": {
                    "path": str(resolved_path),
                    "size": file_size,
                    "lines": line_count,
                    "encoding": encoding,
                    "created": is_new_file
                },
                "summary": (
                    f"{'创建' if is_new_file else '覆写'}成功：{resolved_path.name}，"
                    f"{line_count} 行，{file_size} 字节"
                )
            }

        except Exception as e:
            logger.error("write_file_failed", path=path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "summary": f"写入失败：{str(e)[:80]}"
            }

    def _resolve_path(self, path: str) -> Optional[Path]:
        """
        解析文件路径，确保在工作目录范围内（与 read_file/edit_file 逻辑一致）
        """
        try:
            file_path = Path(path)

            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            file_path = file_path.resolve()

            if not file_path.is_relative_to(self.working_dir):
                logger.warning(
                    "write_file_path_escape",
                    requested_path=path,
                    allowed_dir=str(self.working_dir)
                )
                return None

            return file_path

        except Exception as e:
            logger.error("write_file_path_resolution_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "write_file",
            "description": """创建或覆写文件内容

创建新文件或完全覆写已有文件的内容。
自动创建父目录（如不存在）。

使用场景：
- 创建配置文件、代码文件、文档
- 导出数据到文本文件
- 生成报告、日志等

注意：
- 如果文件已存在，会完全覆写（不是追加）
- 工作目录限制：D:/溯源/ 及其子目录
- 文件大小限制：最大 10MB
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（绝对路径或相对路径）。示例：'D:/溯源/backend/config.json' 或 'backend/output.txt'"
                    },
                    "content": {
                        "type": "string",
                        "description": "文件内容（完整内容，会覆写已有文件）"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "文件编码（默认 utf-8），中文文件可尝试 'gbk'",
                        "default": "utf-8"
                    },
                    "create_dirs": {
                        "type": "boolean",
                        "description": "是否自动创建父目录（默认 True）",
                        "default": True
                    }
                },
                "required": ["path", "content"]
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = WriteFileTool()
