"""
EditFile 工具 V2 - 完整对标 Claude Code 官方实现

改进点（对标官方 FileEditTool.ts + utils.ts）：
1. ✅ 预读取验证（强制要求先read_file）
2. ✅ 引号规范化（弯引号↔直引号自动转换）
3. ✅ Trailing空格处理（自动去除，Markdown除外）
4. ✅ 文件修改检查（时间戳+内容双重验证）
5. ✅ 模糊匹配（findActualString容错机制）
6. ✅ 增强错误提示（显示实际匹配内容）
7. ✅ 行尾符规范化（\r\n → \n）
8. ✅ 编码自动检测（UTF-8 vs UTF-16LE vs GBK）
9. ✅ 文件大小限制（防止OOM）
10. ✅ 多匹配检查（replace_all验证）

使用场景：
- 修改代码文件（.py, .js, .ts 等）
- 更新配置文件（.json, .yaml, .xml 等）
- 替换文档内容（.txt, .md 等）

⚠️ 不适用于：
- Word 文档（.docx）→ 使用 find_replace_word 或 word_edit
- Word XML（document.xml）→ 使用 find_replace_word 或 word_edit

参考：
- Claude Code: src/tools/FileEditTool/FileEditTool.ts
- Claude Code: src/tools/FileEditTool/utils.ts
"""
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.file_read_state import get_file_read_state
import structlog

logger = structlog.get_logger()


# ============================================================================
# 引号常量（LLM无法输出弯引号，所以定义为常量供LLM使用）
# ============================================================================
LEFT_SINGLE_CURLY_QUOTE = '''"'''  # '
RIGHT_SINGLE_CURLY_QUOTE = ''''''   # '
LEFT_DOUBLE_CURLY_QUOTE = '"'      # "
RIGHT_DOUBLE_CURLY_QUOTE = '"'     # "


# ============================================================================
# 工具函数（对标官方 utils.ts）
# ============================================================================

def normalize_quotes(s: str) -> str:
    """
    规范化引号（弯引号 → 直引号）

    参考：utils.ts:normalizeQuotes()
    """
    return (s
        .replace(LEFT_SINGLE_CURLY_QUOTE, "'")
        .replace(RIGHT_SINGLE_CURLY_QUOTE, "'")
        .replace(LEFT_DOUBLE_CURLY_QUOTE, '"')
        .replace(RIGHT_DOUBLE_CURLY_QUOTE, '"'))


def strip_trailing_whitespace(s: str) -> str:
    """
    去除每行末尾空格（保留换行符）

    参考：utils.ts:stripTrailingWhitespace()
    """
    lines = s.split('\n')
    return '\n'.join(line.rstrip() for line in lines)


def find_actual_string(file_content: str, search_string: str) -> Optional[str]:
    """
    模糊匹配：在文件中查找实际字符串（支持引号规范化）

    参考：utils.ts:findActualString()

    Args:
        file_content: 文件内容
        search_string: 要查找的字符串

    Returns:
        实际在文件中找到的字符串（保留原始引号风格），未找到返回 None
    """
    # 1. 尝试精确匹配
    if search_string in file_content:
        return search_string

    # 2. 尝试引号规范化后的匹配
    normalized_search = normalize_quotes(search_string)
    normalized_file = normalize_quotes(file_content)

    try:
        search_index = normalized_file.index(normalized_search)
    except ValueError:
        return None

    # 3. 返回实际在文件中的字符串（保留原始引号风格）
    actual_string = file_content[search_index:search_index + len(search_string)]
    return actual_string


def preserve_quote_style(old_string: str, actual_old_string: str, new_string: str) -> str:
    """
    保留引号风格：如果old_string通过引号规范化匹配，则对new_string应用相同的引号风格

    参考：utils.ts:preserveQuoteStyle()

    Args:
        old_string: LLM提供的原始字符串（直引号）
        actual_old_string: 实际在文件中的字符串（可能有弯引号）
        new_string: LLM提供的新字符串（直引号）

    Returns:
        应用引号风格后的new_string
    """
    # 如果没有发生规范化，直接返回
    if old_string == actual_old_string:
        return new_string

    # 检测文件中使用了哪种弯引号
    has_double_quotes = (LEFT_DOUBLE_CURLY_QUOTE in actual_old_string or
                        RIGHT_DOUBLE_CURLY_QUOTE in actual_old_string)
    has_single_quotes = (LEFT_SINGLE_CURLY_QUOTE in actual_old_string or
                        RIGHT_SINGLE_CURLY_QUOTE in actual_old_string)

    if not has_double_quotes and not has_single_quotes:
        return new_string

    result = new_string

    if has_double_quotes:
        result = _apply_curly_double_quotes(result)
    if has_single_quotes:
        result = _apply_curly_single_quotes(result)

    return result


def _is_opening_context(chars: list, index: int) -> bool:
    """
    判断引号是否是开引号（基于上下文）

    参考：utils.ts:isOpeningContext()
    """
    if index == 0:
        return True

    prev = chars[index - 1]
    return prev in (' ', '\t', '\n', '\r', '(', '[', '{', '\u2014', '\u2013')


def _apply_curly_double_quotes(s: str) -> str:
    """应用双弯引号"""
    chars = list(s)
    result = []
    for i, char in enumerate(chars):
        if char == '"':
            result.append(
                LEFT_DOUBLE_CURLY_QUOTE if _is_opening_context(chars, i)
                else RIGHT_DOUBLE_CURLY_QUOTE
            )
        else:
            result.append(char)
    return ''.join(result)


def _apply_curly_single_quotes(s: str) -> str:
    """应用单弯引号（避免缩写中的撇号）"""
    chars = list(s)
    result = []
    for i, char in enumerate(chars):
        if char == "'":
            # 避免缩写中的撇号（don't, it's 等）
            prev = chars[i - 1] if i > 0 else None
            next_char = chars[i + 1] if i < len(chars) - 1 else None

            # 检查是否是撇号（在两个字母之间）
            prev_is_letter = prev is not None and prev.isalpha()
            next_is_letter = next_char is not None and next_char.isalpha()

            if prev_is_letter and next_is_letter:
                # 缩写中的撇号，使用右单引号
                result.append(RIGHT_SINGLE_CURLY_QUOTE)
            else:
                # 普通引号
                result.append(
                    LEFT_SINGLE_CURLY_QUOTE if _is_opening_context(chars, i)
                    else RIGHT_SINGLE_CURLY_QUOTE
                )
        else:
            result.append(char)
    return ''.join(result)


def normalize_line_endings(content: str) -> str:
    """
    规范化行尾符（\r\n → \n）

    参考：FileEditTool.ts:214
    """
    return content.replace('\r\n', '\n')


def detect_encoding(file_path: Path) -> str:
    """
    自动检测文件编码

    参考：FileEditTool.ts:208-213

    Args:
        file_path: 文件路径

    Returns:
        编码格式（'utf-8' 或 'utf-16-le' 或 'gbk'）
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(2)

            # UTF-16 LE (BOM: FF FE)
            if len(header) >= 2 and header[0] == 0xFF and header[1] == 0xFE:
                return 'utf-16-le'

    except Exception:
        pass

    # 默认UTF-8，如果失败则尝试GBK
    return 'utf-8'


def get_file_modification_time(file_path: Path) -> float:
    """
    获取文件修改时间（Unix时间戳）

    参考：FileEditTool.ts:getFileModificationTime()
    """
    return file_path.stat().st_mtime


# ============================================================================
# EditFile 工具类
# ============================================================================

class EditFileToolV2(LLMTool):
    """
    文件精确编辑工具 V2（完整对标 Claude Code 官方实现）

    核心改进：
    1. 强制预读取验证（必须先调用read_file）
    2. 引号规范化（自动处理弯引号）
    3. Trailing空格处理（自动去除）
    4. 文件修改检查（防止并发冲突）
    5. 模糊匹配（findActualString容错）
    6. 增强错误提示（显示实际内容）
    """

    # 文件大小限制（1GiB，参考官方）
    MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024

    # Markdown文件扩展名（不处理trailing空格）
    MARKDOWN_EXTENSIONS = {'.md', '.mdx', '.markdown'}

    def __init__(self):
        super().__init__(
            name="edit_file",
            description="""精确编辑文件内容（完整对标 Claude Code 官方实现）

⚠️ 重要限制：
- ❌ 不适用于编辑 Word 文档（.docx）！
  - 简单替换 → 使用 find_replace_word 工具
  - 复杂编辑 → 使用 word_edit 工具
- ❌ 不适用于编辑 Word XML 文件（document.xml）！
  - 简单替换 → 使用 find_replace_word 工具
  - 复杂编辑 → 使用 word_edit 工具
- ✅ 适用于：代码文件（.py, .js, .ts 等）、配置文件（.json, .yaml, .xml 等）、文本文件（.txt, .md 等）

核心功能：
1. 强制预读验证：必须先使用 read_file 读取文件
2. 引号规范化：自动处理弯引号（"..." ↔ "..."）
3. Trailing空格处理：自动去除每行末尾空格（Markdown除外）
4. 文件修改检查：检测文件是否在读取后被修改
5. 模糊匹配：支持引号规范化后的容错匹配
6. 增强错误提示：显示实际在文件中找到的内容

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
- encoding: 文件编码（默认 utf-8，自动检测）

⚠️ JSON格式要求（重要）：
- old_string 和 new_string 中的换行符必须写成 \\n（不是真实换行）
- 引号必须写成 \\"
- 反斜杠必须写成 \\\\
- 示例：多行文本应该是 "line1\\nline2\\nline3" 而不是直接换行

注意：
- 必须先使用 read_file 读取文件，否则会报错
- old_string 在文件中不存在时会提供详细诊断信息
- old_string 在文件中出现多次且 replace_all=False 时报错
- 自动处理引号规范化和trailing空格
- 工作目录限制：D:/溯源/ 及其子目录
""",
            category=ToolCategory.QUERY,
            version="2.0.0",
            requires_context=False
        )

        # 工作目录限制（与read_file保持一致，使用项目根目录）
        self.working_dir = Path.cwd().parent

        # 文件读取状态管理器
        self.read_state = get_file_read_state()

    async def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        精确编辑文件内容（完整版）

        Args:
            path: 文件路径
            old_string: 要替换的原内容
            new_string: 替换后的新内容
            replace_all: 是否替换所有匹配项
            encoding: 文件编码（None表示自动检测）

        Returns:
            {
                "success": bool,
                "data": {...},
                "summary": str
            }
        """
        try:
            # ============================================================
            # 1. 路径安全检查
            # ============================================================
            resolved_path = self._resolve_path(path)
            if not resolved_path:
                return {
                    "success": False,
                    "error": f"文件路径无效或超出工作目录范围: {path}",
                    "summary": f"编辑失败：路径不合法 {path}"
                }

            # ============================================================
            # 2. 检查文件存在
            # ============================================================
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

            # ============================================================
            # 3. 文件大小限制检查（防止OOM）
            # ============================================================
            file_size = resolved_path.stat().st_size
            if file_size > self.MAX_EDIT_FILE_SIZE:
                return {
                    "success": False,
                    "error": f"文件过大（{self._format_size(file_size)}），最大支持 {self._format_size(self.MAX_EDIT_FILE_SIZE)}",
                    "summary": f"编辑失败：文件过大"
                }

            # ============================================================
            # 4. 预读取验证（强制要求先read_file）
            # ============================================================
            pre_read_check = self._check_pre_read(resolved_path)
            if not pre_read_check["valid"]:
                return {
                    "success": False,
                    "error": pre_read_check["error"],
                    "summary": pre_read_check["summary"]
                }

            # ============================================================
            # 5. 文件修改检查（时间戳+内容双重验证）
            # ============================================================
            modification_check = self._check_file_modified(resolved_path)
            if not modification_check["valid"]:
                return {
                    "success": False,
                    "error": modification_check["error"],
                    "summary": modification_check["summary"]
                }

            # ============================================================
            # 6. 读取文件内容
            # ============================================================
            read_result = self._read_file_content(resolved_path, encoding)
            if not read_result["success"]:
                return read_result

            content = read_result["content"]
            actual_encoding = read_result["encoding"]

            # ============================================================
            # 7. 检查 old_string 是否存在（使用模糊匹配）
            # ============================================================
            actual_old_string = find_actual_string(content, old_string)
            if actual_old_string is None:
                return self._create_not_found_error(
                    resolved_path, content, old_string
                )

            # ============================================================
            # 8. 多匹配检查
            # ============================================================
            count = content.count(actual_old_string)
            if count > 1 and not replace_all:
                return {
                    "success": False,
                    "error": f"old_string 在文件中出现了 {count} 次，请设置 replace_all=True 替换全部，或提供更多上下文使 old_string 唯一",
                    "data": {
                        "occurrence_count": count,
                        "old_string_preview": old_string[:100],
                        "actual_old_string_preview": actual_old_string[:100]
                    },
                    "summary": f"编辑失败：old_string 不唯一（出现 {count} 次），请使用 replace_all=True 或扩大匹配范围"
                }

            # ============================================================
            # 9. 规范化 new_string（引号风格+trailing空格）
            # ============================================================
            actual_new_string = self._normalize_new_string(
                resolved_path,
                old_string,
                actual_old_string,
                new_string
            )

            # ============================================================
            # 10. 执行替换
            # ============================================================
            if replace_all:
                new_content = content.replace(actual_old_string, actual_new_string)
                changes = count
            else:
                new_content = content.replace(actual_old_string, actual_new_string, 1)
                changes = 1

            # ============================================================
            # 11. 写回文件
            # ============================================================
            resolved_path.write_text(new_content, encoding=actual_encoding)

            # ============================================================
            # 12. 更新读取状态
            # ============================================================
            self.read_state.set(
                str(resolved_path),
                content=new_content,
                file_size=len(new_content),
                encoding=actual_encoding
            )

            logger.info(
                "edit_file_v2_success",
                file=str(resolved_path),
                changes=changes,
                replace_all=replace_all,
                encoding=actual_encoding
            )

            return {
                "success": True,
                "data": {
                    "path": str(resolved_path),
                    "changes": changes,
                    "old_string_preview": actual_old_string[:80] + ("..." if len(actual_old_string) > 80 else ""),
                    "new_string_preview": actual_new_string[:80] + ("..." if len(actual_new_string) > 80 else ""),
                    "replace_all": replace_all,
                    "encoding": actual_encoding
                },
                "summary": f"编辑成功：{resolved_path.name}，替换了 {changes} 处"
            }

        except Exception as e:
            logger.error("edit_file_v2_failed", path=path, error=str(e), exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "summary": f"编辑失败：{str(e)[:80]}"
            }

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _resolve_path(self, path: str) -> Optional[Path]:
        """解析文件路径，确保在工作目录范围内"""
        try:
            file_path = Path(path)

            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            file_path = file_path.resolve()

            if not file_path.is_relative_to(self.working_dir):
                logger.warning(
                    "edit_file_v2_path_escape",
                    requested_path=path,
                    allowed_dir=str(self.working_dir)
                )
                return None

            return file_path

        except Exception as e:
            logger.error("edit_file_v2_path_resolution_failed", path=path, error=str(e))
            return None

    def _check_pre_read(self, file_path: Path) -> Dict[str, Any]:
        """
        预读取验证（强制要求先read_file）

        参考：FileEditTool.ts:275-286
        """
        read_record = self.read_state.get(str(file_path))

        if read_record is None or read_record.is_partial_view:
            return {
                "valid": False,
                "error": "File has not been read yet. Use read_file first before editing.",
                "summary": "编辑失败：请先使用 read_file 读取文件"
            }

        return {"valid": True}

    def _check_file_modified(self, file_path: Path) -> Dict[str, Any]:
        """
        文件修改检查（时间戳+内容双重验证）

        参考：FileEditTool.ts:290-310
        """
        read_record = self.read_state.get(str(file_path))
        if read_record is None:
            return {"valid": True}  # 已经在_pre_read_check中处理

        current_mtime = get_file_modification_time(file_path)

        if current_mtime > read_record.timestamp:
            # 时间戳表明文件被修改，进行内容验证
            if read_record.is_full_read and read_record.content:
                try:
                    current_content = file_path.read_text(encoding=read_record.encoding)
                    if current_content == read_record.content:
                        # 内容未变，安全继续（可能是云同步/杀毒软件导致的 timestamp 变化）
                        return {"valid": True}
                except Exception:
                    pass

            # 内容确实变了，拒绝编辑
            return {
                "valid": False,
                "error": "File has been modified since read. Read it again before editing.",
                "summary": "编辑失败：文件在读取后被修改，请重新读取"
            }

        return {"valid": True}

    def _read_file_content(self, file_path: Path, encoding: Optional[str]) -> Dict[str, Any]:
        """
        读取文件内容（自动检测编码+规范化行尾符）

        参考：FileEditTool.ts:206-221
        """
        try:
            # 自动检测编码
            if encoding is None:
                encoding = detect_encoding(file_path)

            # 读取文件
            content = file_path.read_text(encoding=encoding)

            # 规范化行尾符（\r\n → \n）
            content = normalize_line_endings(content)

            return {
                "success": True,
                "content": content,
                "encoding": encoding
            }

        except UnicodeDecodeError:
            # 尝试GBK编码
            try:
                content = file_path.read_text(encoding='gbk')
                content = normalize_line_endings(content)
                return {
                    "success": True,
                    "content": content,
                    "encoding": 'gbk'
                }
            except Exception:
                return {
                    "success": False,
                    "error": "文件编码错误，尝试了 utf-8 和 gbk",
                    "summary": "编辑失败：编码错误"
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "summary": f"编辑失败：{str(e)[:80]}"
            }

    def _normalize_new_string(
        self,
        file_path: Path,
        old_string: str,
        actual_old_string: str,
        new_string: str
    ) -> str:
        """
        规范化 new_string（引号风格+trailing空格）

        参考：FileEditTool.ts:474-479
        """
        # 1. 保留引号风格
        result = preserve_quote_style(old_string, actual_old_string, new_string)

        # 2. 处理trailing空格（Markdown除外）
        is_markdown = file_path.suffix.lower() in self.MARKDOWN_EXTENSIONS
        if not is_markdown:
            result = strip_trailing_whitespace(result)

        return result

    def _create_not_found_error(
        self,
        file_path: Path,
        content: str,
        old_string: str
    ) -> Dict[str, Any]:
        """
        创建未找到错误（带详细诊断信息）

        参考：FileEditTool.ts:318-327
        """
        # 检测是否是 Word XML 文件
        is_word_xml = "document.xml" in file_path.name and file_path.parent.name == "word"

        # 提供文件预览
        preview = content[:200].replace('\n', '\\n')

        # 构建hints
        hints = [
            "1. old_string 必须与文件内容完全一致（包括空格、缩进、换行、标点符号）",
            "2. 建议先用 read_file 查看文件的实际内容，确保 old_string 匹配"
        ]

        # 如果是 Word XML，添加特殊提示
        if is_word_xml:
            hints.insert(0, "⚠️ 检测到这是 Word XML 文件！")
            hints.insert(1, "   简单文本替换：使用 find_replace_word 工具（直接操作 .docx 文件）")
            hints.insert(2, "   复杂结构编辑：使用 word_edit 工具（自动解包/编辑/打包）")

        # 尝试引号规范化后的匹配
        normalized_old = normalize_quotes(old_string)
        normalized_content = normalize_quotes(content)

        if normalized_old in normalized_content:
            hints.append("")
            hints.append("💡 提示：文件中使用了弯引号（""''），old_string 使用了直引号（\"\"'')")
            hints.append("   工具会自动处理引号规范化，请确保 old_string 的其他部分（空格、缩进）完全一致")

        return {
            "success": False,
            "error": "old_string 在文件中不存在",
            "data": {
                "file_preview": preview,
                "old_string_preview": old_string[:100],
                "file_type": "word_xml" if is_word_xml else ("xml" if "<" in content else "text"),
                "hints": hints,
                "is_quote_mismatch": normalized_old in normalized_content and old_string not in content
            },
            "summary": f"编辑失败：old_string 未找到（文件: {file_path.name}）"
        }

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "edit_file",
            "description": """精确编辑文件内容（完整对标 Claude Code 官方实现）

⚠️ 不适用于编辑 Word 文档！
- 简单文本替换 → 使用 find_replace_word 工具
- 复杂结构编辑 → 使用 word_edit 工具

核心功能：
1. 强制预读验证：必须先使用 read_file 读取文件
2. 引号规范化：自动处理弯引号（"..." ↔ "..."）
3. Trailing空格处理：自动去除每行末尾空格（Markdown除外）
4. 文件修改检查：检测文件是否在读取后被修改
5. 模糊匹配：支持引号规范化后的容错匹配

使用场景：修改代码文件（.py, .js 等）、配置文件（.json, .yaml 等）、文本文件。

⚠️ JSON格式要求（重要）：
- old_string 和 new_string 中的换行符必须写成 \\n（不是真实换行）
- 引号必须写成 \\"
- 反斜杠必须写成 \\\\
- 示例：多行文本应该是 "line1\\nline2\\nline3" 而不是直接换行

注意：
- ❌ 不要用于编辑 Word 文档（.docx）或 Word XML（document.xml）
- ✅ 用于编辑代码、配置、文本文件
- 必须先使用 read_file 读取文件
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
                        "description": "要替换的原内容（必须与文件完全一致，包括空格、缩进、换行符）。注意：JSON字符串中换行符需用\\\\n转义，引号需用\\\\\"转义。工具会自动处理引号规范化（弯引号↔直引号）和trailing空格。"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的新内容。注意：JSON字符串中换行符需用\\\\n转义，引号需用\\\\\"转义。工具会自动保留文件的引号风格和处理trailing空格。"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "是否替换所有匹配项（默认 False，仅替换第一个）。当 old_string 在文件中出现多次时需设为 True",
                        "default": False
                    },
                    "encoding": {
                        "type": "string",
                        "description": "文件编码（默认 None 表示自动检测），支持 utf-8、gbk、utf-16-le",
                        "default": None
                    }
                },
                "required": ["path", "old_string", "new_string"]
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = EditFileToolV2()
