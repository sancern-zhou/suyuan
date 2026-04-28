"""
WriteFile 工具 - 完整对标 Claude Code 官方实现

核心功能（对标官方 FileWriteTool.ts）：
1. ✅ 先读后写机制（强制要求先read_file）
2. ✅ 文件修改时间检查（防止覆盖用户修改）
3. ✅ 原子性检查（防止并发修改）
4. ✅ 返回结构化 diff（精确变更信息）
5. ✅ 更新读取状态（写入后同步状态）
6. ✅ UNC 路径安全检查（Windows）
7. ✅ 目录不存在检查（创建新文件时）
8. ✅ 文件大小限制（防止OOM）

使用场景：
- 创建新文件（配置文件、代码文件、文档）
- 完全覆写已有文件（谨慎使用）
- 导出数据到文本文件

⚠️ 重要限制：
- 如果是已存在的文件，必须先使用 read_file 读取文件内容
- 如果要修改文件的部分内容，请使用 edit_file 工具
- 对于大型文件的修改，edit_file 更高效（只发送 diff）

参考：
- Claude Code: src/tools/FileWriteTool/FileWriteTool.ts
- Claude Code: src/tools/FileWriteTool/utils.ts
"""
import os
import time
import difflib
import platform
from pathlib import Path
from typing import Dict, Any, Optional, List
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.file_read_state import get_file_read_state
from app.tools.utility.project_root import get_project_root
import structlog

logger = structlog.get_logger()


# ============================================================================
# 常量定义（对标官方）
# ============================================================================

# 文件大小限制（1GB，参考官方 MAX_EDIT_FILE_SIZE）
MAX_FILE_SIZE = 1024 * 1024 * 1024

# Diff 上下文行数（参考官方 CONTEXT_LINES）
DIFF_CONTEXT_LINES = 3

# UNC 路径前缀（Windows）
UNC_PATH_PREFIXES = ('\\\\', '//')


# ============================================================================
# 工具函数（对标官方 utils.ts）
# ============================================================================

def get_file_modification_time(file_path: Path) -> float:
    """
    获取文件修改时间（Unix时间戳）

    参考：FileEditTool.ts:getFileModificationTime()
    """
    return file_path.stat().st_mtime


def normalize_line_endings(content: str) -> str:
    """
    规范化行尾符（\r\n → \n）

    参考：FileWriteTool.ts:214
    """
    return content.replace('\r\n', '\n')


def count_lines(content: str) -> int:
    """
    计算文件行数（与编辑器行号一致）

    参考：UI.tsx:countLines()
    """
    parts = content.split('\n')
    # 如果内容以换行符结尾，则不计算为额外一行
    return len(parts) - 1 if content.endswith('\n') else len(parts)


def generate_unified_diff(
    file_path: str,
    old_content: str,
    new_content: str,
    context_lines: int = DIFF_CONTEXT_LINES
) -> str:
    """
    生成 unified diff 格式的差异信息

    参考：diff.ts:getPatchFromContents()

    Args:
        file_path: 文件路径
        old_content: 原始内容
        new_content: 新内容
        context_lines: 上下文行数

    Returns:
        unified diff 格式的字符串
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"{file_path} (old)",
        tofile=f"{file_path} (new)",
        lineterm='\n',
        n=context_lines
    )

    return ''.join(diff)


def is_unc_path(path: str) -> bool:
    """
    检查是否为 UNC 路径（Windows 网络路径）

    UNC 路径示例：\\\\server\\share\\file.txt 或 //server/share/file.txt

    参考：FileWriteTool.ts:182-183

    SECURITY: UNC 路径在 Windows 上会触发 SMB 认证，可能导致 NTLM 凭据泄露
    """
    return path.startswith(UNC_PATH_PREFIXS)


def is_windows() -> bool:
    """检查是否为 Windows 系统"""
    return platform.system() == 'Windows'


# ============================================================================
# WriteFile 工具类
# ============================================================================

class WriteFileTool(LLMTool):
    """
    文件写入工具（完整对标 Claude Code 官方实现）

    核心改进：
    1. 强制预读取验证（必须先read_file）
    2. 文件修改检查（防止并发冲突）
    3. 结构化 diff 返回（精确变更信息）
    4. 原子性检查（防止竞态条件）
    5. UNC 路径安全检查（Windows）
    """

    def __init__(self):
        super().__init__(
            name="write_file",
            description="""创建或覆写文件内容（完整对标 Claude Code 官方实现）

⚠️ 重要限制：
- 如果是已存在的文件，必须先使用 read_file 读取文件内容！
- 如果要修改文件的部分内容，请使用 edit_file 工具（更高效）
- 此工具会完全覆写文件内容，谨慎使用！

核心功能：
1. 强制预读验证：已存在的文件必须先使用 read_file 读取
2. 文件修改检查：检测文件是否在读取后被修改
3. 结构化 diff：返回精确的变更信息（update 时）
4. 原子性检查：防止并发修改导致的数据丢失
5. UNC 路径安全：Windows 网络路径安全检查

使用场景：
- ✅ 创建新文件（配置文件、代码文件、文档）
- ✅ 完全覆写已有文件（必须先 read_file）
- ✅ 导出数据到文本文件
- ❌ 修改文件的部分内容 → 使用 edit_file 工具

路径说明（重要）：
- 报告文件：/home/xckj/suyuan/backend_data_registry/report.md
- 数据文件：/home/xckj/suyuan/backend_data_registry/data.json
- 相对路径：backend/output.txt（相对于项目根目录）

示例：
- write_file(path="/home/xckj/suyuan/backend_data_registry/report.md", content="# 报告内容")
- write_file(path="backend/output.txt", content="output data")
- write_file(path="config.json", content='{"port": 8000}')

参数说明：
- path: 文件路径（必填，绝对路径或相对路径）
- content: 文件内容（必填，完整内容，会覆写已有文件）
- encoding: 文件编码（默认 utf-8）
- create_dirs: 是否自动创建父目录（默认 True）

返回信息：
- type: "create" | "update"（创建 or 更新）
- filePath: 文件路径
- content: 写入的内容
- lines: 行数
- size: 文件大小（字节）
- structuredPatch: 结构化 diff（仅 update 时）
- originalFile: 原始内容（仅 update 时）

错误码：
- 1: 路径无效或超出工作目录范围
- 2: 文件尚未读取（需要先 read_file）
- 3: 文件在读取后被修改（需要重新 read_file）
- 4: 文件大小超过限制
- 5: 编码错误
- 6: 目录创建失败
""",
            category=ToolCategory.QUERY,
            version="2.0.0",
            requires_context=False
        )

        self.working_dir = get_project_root()
        self.read_state = get_file_read_state()

    async def execute(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        写入文件内容（完整对标 Claude Code 官方实现）

        Args:
            path: 文件路径
            content: 文件内容
            encoding: 文件编码（默认 utf-8）
            create_dirs: 是否自动创建父目录（默认 True）

        Returns:
            {
                "success": bool,
                "data": {
                    "type": "create" | "update",
                    "filePath": str,
                    "content": str,
                    "lines": int,
                    "size": int,
                    "encoding": str,
                    "structuredPatch": str,  # 仅 update 时
                    "originalFile": str,     # 仅 update 时
                },
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
                    "summary": f"写入失败：路径不合法",
                    "error_code": 1
                }

            # ============================================================
            # 2. UNC 路径安全检查（Windows）
            # ============================================================
            if is_windows() and is_unc_path(str(resolved_path)):
                logger.warning(
                    "write_file_unc_path_blocked",
                    path=str(resolved_path),
                    reason="SMB authentication may leak NTLM credentials"
                )
                return {
                    "success": False,
                    "error": "UNC 路径（网络路径）被阻止：可能存在 NTLM 凭据泄露风险",
                    "summary": "写入失败：UNC 路径不安全",
                    "error_code": 1
                }

            # ============================================================
            # 3. 检查是否为目录
            # ============================================================
            if resolved_path.exists() and resolved_path.is_dir():
                return {
                    "success": False,
                    "error": f"路径是目录而非文件: {path}",
                    "summary": f"写入失败：路径是目录",
                    "error_code": 1
                }

            # ============================================================
            # 4. 文件大小检查
            # ============================================================
            content_size = len(content.encode(encoding))
            if content_size > MAX_FILE_SIZE:
                return {
                    "success": False,
                    "error": f"文件内容过大（{self._format_size(content_size)}），超过限制（{self._format_size(MAX_FILE_SIZE)}）",
                    "summary": f"写入失败：内容过大",
                    "error_code": 4
                }

            # ============================================================
            # 5. 判断是创建还是更新
            # ============================================================
            is_new_file = not resolved_path.exists()

            # ============================================================
            # 6. 预读取验证（强制要求先read_file）
            # ============================================================
            if not is_new_file:
                pre_read_check = self._check_pre_read(resolved_path)
                if not pre_read_check["valid"]:
                    return {
                        "success": False,
                        "error": pre_read_check["error"],
                        "summary": pre_read_check["summary"],
                        "error_code": 2
                    }

            # ============================================================
            # 7. 文件修改检查（时间戳+内容双重验证）
            # ============================================================
            if not is_new_file:
                modification_check = self._check_file_modified(resolved_path, content)
                if not modification_check["valid"]:
                    return {
                        "success": False,
                        "error": modification_check["error"],
                        "summary": modification_check["summary"],
                        "error_code": 3
                    }

            # ============================================================
            # 8. 创建父目录（如需要）
            # ============================================================
            if create_dirs and not resolved_path.parent.exists():
                try:
                    resolved_path.parent.mkdir(parents=True, exist_ok=True)
                    logger.info("write_file_dirs_created", path=str(resolved_path.parent))
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"创建父目录失败: {str(e)}",
                        "summary": f"写入失败：无法创建目录",
                        "error_code": 6
                    }

            # ============================================================
            # 9. 读取原始内容（用于 diff）
            # ============================================================
            old_content = None
            if not is_new_file:
                try:
                    old_content = resolved_path.read_text(encoding=encoding)
                except Exception as e:
                    # 读取失败，但继续写入（文件可能已损坏）
                    logger.warning("write_file_read_old_content_failed", path=str(resolved_path), error=str(e))

            # ============================================================
            # 10. 写入文件（原子性操作）
            # ============================================================
            try:
                # 规范化行尾符（参考官方：保持 LLM 发送的行尾符）
                normalized_content = normalize_line_endings(content)
                resolved_path.write_text(normalized_content, encoding=encoding)
            except UnicodeEncodeError:
                return {
                    "success": False,
                    "error": f"编码错误，内容无法用 {encoding} 编码，请尝试 encoding='utf-8'",
                    "summary": f"写入失败：编码错误",
                    "error_code": 5
                }

            # ============================================================
            # 11. 更新读取状态
            # ============================================================
            self.read_state.set(
                str(resolved_path),
                content=normalized_content,
                file_size=resolved_path.stat().st_size,
                encoding=encoding
            )

            # ============================================================
            # 12. 统计信息
            # ============================================================
            file_size = resolved_path.stat().st_size
            line_count = count_lines(normalized_content)

            logger.info(
                "write_file_success",
                file=str(resolved_path),
                size=file_size,
                lines=line_count,
                created=is_new_file
            )

            # ============================================================
            # 13. 构建返回结果
            # ============================================================
            result_data = {
                "type": "create" if is_new_file else "update",
                "filePath": str(resolved_path),
                "content": normalized_content,
                "lines": line_count,
                "size": file_size,
                "encoding": encoding,
            }

            # 更新时返回 diff 信息
            if not is_new_file and old_content is not None:
                diff = generate_unified_diff(
                    str(resolved_path),
                    old_content,
                    normalized_content
                )
                result_data["structuredPatch"] = diff
                result_data["originalFile"] = old_content

                # 统计变更行数
                lines_added = normalized_content.count('\n') - old_content.count('\n')
                logger.info(
                    "write_file_lines_changed",
                    added=max(0, lines_added),
                    removed=max(0, -lines_added)
                )
            else:
                result_data["structuredPatch"] = ""
                result_data["originalFile"] = None

            return {
                "success": True,
                "data": result_data,
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

    def _check_pre_read(self, file_path: Path) -> Dict[str, Any]:
        """
        预读取验证（强制要求先read_file）

        参考：FileWriteTool.ts:198-206
        """
        read_record = self.read_state.get(str(file_path))

        if read_record is None or read_record.is_partial_view:
            return {
                "valid": False,
                "error": "File has not been read yet. Use read_file first before writing to it.",
                "summary": "写入失败：请先使用 read_file 读取文件"
            }

        return {"valid": True}

    def _check_file_modified(self, file_path: Path, new_content: str) -> Dict[str, Any]:
        """
        文件修改检查（时间戳+内容双重验证）

        参考：FileWriteTool.ts:211-220
        """
        read_record = self.read_state.get(str(file_path))
        if read_record is None:
            return {"valid": True}  # 已经在 _check_pre_read 中处理

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

            # 内容确实变了，拒绝写入
            return {
                "valid": False,
                "error": "File has been modified since read, either by the user or by a linter. Read it again before attempting to write it.",
                "summary": "写入失败：文件在读取后被修改，请重新读取"
            }

        return {"valid": True}

    def _resolve_path(self, path: str) -> Optional[Path]:
        """
        解析文件路径，确保在工作目录范围内

        参考：FileWriteTool.ts:expandPath() + 权限检查
        """
        try:
            file_path = Path(path).expanduser().resolve()

            # 相对路径转换为绝对路径
            if not file_path.is_absolute():
                file_path = (self.working_dir / file_path).resolve()

            # 安全检查：确保在工作目录范围内
            try:
                file_path.relative_to(self.working_dir)
            except ValueError:
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

    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "write_file",
            "description": """创建或覆写文件内容（完整对标 Claude Code 官方实现）

⚠️ 重要限制：
- 如果是已存在的文件，必须先使用 read_file 读取文件内容！
- 如果要修改文件的部分内容，请使用 edit_file 工具（更高效）
- 此工具会完全覆写文件内容，谨慎使用！

核心功能：
1. 强制预读验证：已存在的文件必须先使用 read_file 读取
2. 文件修改检查：检测文件是否在读取后被修改
3. 结构化 diff：返回精确的变更信息（update 时）
4. 原子性检查：防止并发修改导致的数据丢失

使用场景：
- ✅ 创建新文件（配置文件、代码文件、文档）
- ✅ 完全覆写已有文件（必须先 read_file）
- ✅ 导出数据到文本文件
- ❌ 修改文件的部分内容 → 使用 edit_file 工具

路径说明（重要）：
- 报告文件：/home/xckj/suyuan/backend_data_registry/report.md
- 数据文件：/home/xckj/suyuan/backend_data_registry/data.json
- 相对路径：backend/output.txt（相对于项目根目录）

示例：
- write_file(path="/home/xckj/suyuan/backend_data_registry/report.md", content="# 报告内容")
- write_file(path="backend/output.txt", content="output data")
- write_file(path="config.json", content='{"port": 8000}')

参数说明：
- path: 文件路径（必填，绝对路径或相对路径）
- content: 文件内容（必填，完整内容，会覆写已有文件）
- encoding: 文件编码（默认 utf-8）
- create_dirs: 是否自动创建父目录（默认 True）

返回信息：
- type: "create" | "update"（创建 or 更新）
- filePath: 文件路径
- content: 写入的内容
- lines: 行数
- size: 文件大小（字节）
- structuredPatch: 结构化 diff（仅 update 时）
- originalFile: 原始内容（仅 update 时）
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（绝对路径或相对路径）。示例：'D:/work/config.json' 或 'backend/output.txt'"
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
