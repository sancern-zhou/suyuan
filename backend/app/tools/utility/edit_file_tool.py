"""
EditFile 工具 - 精确编辑文件内容

通过精确字符串匹配替换文件内容，类似 Claude Code 的 Edit 工具：
- old_string 必须与文件中的内容完全一致（包括缩进、换行）
- 默认要求 old_string 在文件中唯一出现（避免误改）
- replace_all=True 时替换所有匹配项

使用场景：
- 修改代码文件（函数、变量、逻辑）
- 更新配置文件（参数值、路径）
- 替换文档内容（标题、段落）
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()


class EditFileTool(LLMTool):
    """
    文件精确编辑工具

    功能：
    - 精确字符串匹配替换（old_string → new_string）
    - 唯一性验证（防止误改多处）
    - 支持全量替换（replace_all=True）
    - 路径安全检查（限制在工作目录内）
    """

    def __init__(self):
        super().__init__(
            name="edit_file",
            description="""精确编辑文件内容（通过字符串替换）

⚠️ 重要限制：
- ❌ 不适用于编辑 Word 文档（.docx）！
  - 简单替换 → 使用 find_replace_word 工具
  - 复杂编辑 → 使用 word_edit 工具
- ❌ 不适用于编辑 Word XML 文件（document.xml）！
  - 简单替换 → 使用 find_replace_word 工具
  - 复杂编辑 → 使用 word_edit 工具
- ✅ 适用于：代码文件（.py, .js, .ts 等）、配置文件（.json, .yaml, .xml 等）、文本文件（.txt, .md 等）

功能：
- 找到文件中精确匹配 old_string 的内容，替换为 new_string
- old_string 必须与文件内容完全一致（包括空格、缩进、换行）
- 默认要求 old_string 只出现一次（防止误改），多处出现时需要 replace_all=True

使用场景：
- ✅ 修改代码（函数体、变量值、导入语句）
- ✅ 更新配置文件（端口、路径、参数）
- ✅ 编辑文本文件（Markdown、TXT、JSON、YAML 等）
- ❌ 编辑 Word 文档（简单替换用 find_replace_word，复杂编辑用 word_edit）

示例：
- edit_file(path="D:/work/config.py", old_string="PORT = 8000", new_string="PORT = 9000")
- edit_file(path="D:/work/main.py", old_string="def old_func():\\n    pass", new_string="def new_func():\\n    return True")
- edit_file(path="D:/work/log.txt", old_string="ERROR", new_string="WARNING", replace_all=True)

参数说明：
- path: 文件路径（必填）
- old_string: 要替换的原内容（必填，必须与文件完全一致）
- new_string: 替换后的新内容（必填）
- replace_all: 是否替换所有匹配项（默认 False，仅替换第一个）
- encoding: 文件编码（默认 utf-8）

⚠️ JSON格式要求（重要）：
- old_string 和 new_string 中的换行符必须写成 \\n（不是真实换行）
- 引号必须写成 \\"
- 反斜杠必须写成 \\\\
- 示例：多行文本应该是 "line1\\nline2\\nline3" 而不是直接换行

注意：
- old_string 在文件中不存在时会提供详细诊断信息
- old_string 在文件中出现多次且 replace_all=False 时报错
- 工作目录限制：D:/溯源/ 及其子目录
- 编辑 Word 文档请使用 find_replace_word 工具（直接操作 .docx 文件，保留格式）
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        # 工作目录限制（与 read_file 一致）
        # 工作目录限制（与 read_file 一致）
        self.working_dir = Path.cwd().parent  # D:\溯源\ 或 /opt/app/ 等

        # 临时允许的额外目录（用于处理 /tmp 等临时文件）
        self.allowed_dirs = [
            self.working_dir,
            Path("/tmp")  # 临时允许访问 /tmp 目录
        ]

    async def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
        **kwargs
    ) -> Dict[str, Any]:
        """
        精确编辑文件内容

        Args:
            path: 文件路径
            old_string: 要替换的原内容（必须与文件完全一致）
            new_string: 替换后的新内容
            replace_all: 是否替换所有匹配项（默认 False）
            encoding: 文件编码（默认 utf-8）

        Returns:
            {
                "success": bool,
                "data": {
                    "path": str,
                    "changes": int,       # 替换次数
                    "old_string": str,    # 被替换的内容（前50字符）
                    "new_string": str,    # 新内容（前50字符）
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
                    "summary": f"编辑失败：路径不合法 {path}"
                }

            # 2. 检查文件存在
            if not resolved_path.exists():
                return {
                    "success": False,
                    "error": f"文件不存在: {path}",
                    "summary": f"编辑失败：文件不存在 {path}"
                }

            if resolved_path.is_dir():
                return {
                    "success": False,
                    "error": f"路径是目录而非文件: {path}",
                    "summary": f"编辑失败：路径是目录"
                }

            # 3. 读取文件内容
            try:
                content = resolved_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                return {
                    "success": False,
                    "error": f"文件编码错误，请尝试 encoding='gbk'",
                    "summary": f"编辑失败：编码错误 {resolved_path.name}"
                }

            # 4. 检查 old_string 是否存在
            count = content.count(old_string)
            if count == 0:
                # 检测是否是 Word XML 文件
                is_word_xml = "document.xml" in str(resolved_path) and resolved_path.parent.name == "word"

                # 提供诊断信息
                preview = content[:200].replace('\n', '\\n')

                # 构建 hints 数组
                hints = [
                    "1. old_string 必须与文件内容完全一致（包括空格、缩进、换行、标点符号）",
                    "2. 建议先用 read_file 查看文件的实际内容，确保 old_string 匹配"
                ]

                # 如果是 Word XML，添加特殊提示
                if is_word_xml:
                    hints.insert(0, "⚠️ 检测到这是 Word XML 文件！")
                    hints.insert(1, "   简单文本替换：使用 find_replace_word 工具（直接操作 .docx 文件）")
                    hints.insert(2, "   复杂结构编辑：使用 word_edit 工具（自动解包/编辑/打包）")
                    hints.insert(3, "   如果坚持编辑 XML，必须使用 read_file(path=..., raw_mode=True) 读取原始 XML")

                # 如果文件包含 XML 标签但 old_string 不包含，可能是格式不匹配
                if "<w:" in content or "<w:p" in content or "<w:t" in content:
                    if not old_string.startswith("<"):
                        hints.append("   文件是 XML 格式，但 old_string 是纯文本格式，无法匹配！")

                return {
                    "success": False,
                    "error": f"old_string 在文件中不存在",
                    "data": {
                        "file_preview": preview,
                        "old_string_preview": old_string[:100],
                        "file_type": "word_xml" if is_word_xml else ("xml" if "<" in content else "text"),
                        "hints": hints
                    },
                    "summary": f"编辑失败：old_string 未找到（文件: {resolved_path.name}）"
                }

            # 5. 唯一性检查
            if count > 1 and not replace_all:
                return {
                    "success": False,
                    "error": f"old_string 在文件中出现了 {count} 次，请设置 replace_all=True 替换全部，或提供更多上下文使 old_string 唯一",
                    "data": {
                        "occurrence_count": count,
                        "old_string_preview": old_string[:100]
                    },
                    "summary": f"编辑失败：old_string 不唯一（出现 {count} 次），请使用 replace_all=True 或扩大匹配范围"
                }

            # 6. 执行替换
            if replace_all:
                new_content = content.replace(old_string, new_string)
                changes = count
            else:
                new_content = content.replace(old_string, new_string, 1)
                changes = 1

            # 7. 写回文件
            resolved_path.write_text(new_content, encoding=encoding)

            logger.info(
                "edit_file_success",
                file=str(resolved_path),
                changes=changes,
                replace_all=replace_all
            )

            return {
                "success": True,
                "data": {
                    "path": str(resolved_path),
                    "changes": changes,
                    "old_string_preview": old_string[:80] + ("..." if len(old_string) > 80 else ""),
                    "new_string_preview": new_string[:80] + ("..." if len(new_string) > 80 else ""),
                    "replace_all": replace_all
                },
                "summary": f"编辑成功：{resolved_path.name}，替换了 {changes} 处"
            }

        except Exception as e:
            logger.error("edit_file_failed", path=path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "summary": f"编辑失败：{str(e)[:80]}"
            }

    def _resolve_path(self, path: str) -> Optional[Path]:
        """
        解析文件路径，确保在允许的目录范围内
        """
        try:
            file_path = Path(path)

            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            file_path = file_path.resolve()

            # 检查是否在任一允许的目录范围内
            is_allowed = any(file_path.is_relative_to(allowed_dir) for allowed_dir in self.allowed_dirs)

            if not is_allowed:
                allowed_dirs_str = ", ".join(str(d) for d in self.allowed_dirs)
                logger.warning(
                    "edit_file_path_escape",
                    requested_path=path,
                    allowed_dirs=allowed_dirs_str
                )
                return None

            return file_path

        except Exception as e:
            logger.error("edit_file_path_resolution_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "edit_file",
            "description": """精确编辑文件内容（通过字符串替换）

⚠️ 不适用于编辑 Word 文档！
- 简单文本替换 → 使用 find_replace_word 工具
- 复杂结构编辑 → 使用 word_edit 工具

找到文件中精确匹配 old_string 的内容，替换为 new_string。
old_string 必须与文件内容完全一致（包括空格、缩进、换行）。
默认只替换第一个匹配项，且要求唯一（防止误改多处）。

使用场景：修改代码文件（.py, .js 等）、配置文件（.json, .yaml 等）、文本文件。

⚠️ JSON格式要求（重要）：
- old_string 和 new_string 中的换行符必须写成 \\n（不是真实换行）
- 引号必须写成 \\"
- 反斜杠必须写成 \\\\
- 示例：多行文本应该是 "line1\\nline2\\nline3" 而不是直接换行

注意：
- ❌ 不要用于编辑 Word 文档（.docx）或 Word XML（document.xml）
- ✅ 用于编辑代码、配置、文本文件
- old_string 必须完全匹配文件中的内容
- 出现多次时需要 replace_all=True 或扩大 old_string 范围
- 工作目录限制：D:/溯源/ 及其子目录
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（绝对路径或相对路径）。示例：'D:/溯源/backend/app/main.py' 或 'backend/config.py'"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要替换的原内容（必须与文件完全一致，包括空格、缩进、换行符）。注意：JSON字符串中换行符需用\\\\n转义，引号需用\\\\\"转义"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的新内容。注意：JSON字符串中换行符需用\\\\n转义，引号需用\\\\\"转义"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "是否替换所有匹配项（默认 False，仅替换第一个）。当 old_string 在文件中出现多次时需设为 True",
                        "default": False
                    },
                    "encoding": {
                        "type": "string",
                        "description": "文件编码（默认 utf-8），中文文件可尝试 'gbk'",
                        "default": "utf-8"
                    }
                },
                "required": ["path", "old_string", "new_string"]
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = EditFileTool()
