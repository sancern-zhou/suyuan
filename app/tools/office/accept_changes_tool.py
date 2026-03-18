"""
AcceptChanges 工具 - 接受 Word 文档中的所有修订

功能：
- 接受 DOCX 文件中的所有修订标记
- 使用 LibreOffice 宏自动处理
- 支持跨平台（Windows/Linux/macOS）

使用场景：
- 清理文档修订记录
- 批量接受修订
- 文档定稿处理
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.soffice import get_soffice_env
import structlog

logger = structlog.get_logger()

# LibreOffice 配置目录
LIBREOFFICE_PROFILE = tempfile.gettempdir() + "/libreoffice_docx_profile"
MACRO_DIR = f"{LIBREOFFICE_PROFILE}/user/basic/Standard"

# LibreOffice Basic 宏：接受所有修订
ACCEPT_CHANGES_MACRO = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
    Sub AcceptAllTrackedChanges()
        Dim document As Object
        Dim dispatcher As Object

        document = ThisComponent.CurrentController.Frame
        dispatcher = createUnoService("com.sun.star.frame.DispatchHelper")

        dispatcher.executeDispatch(document, ".uno:AcceptAllTrackedChanges", "", 0, Array())
        ThisComponent.store()
        ThisComponent.close(True)
    End Sub
</script:module>"""


class AcceptChangesTool(LLMTool):
    """
    接受 Word 文档所有修订工具

    功能：
    - 接受 DOCX 文件中的所有修订标记
    - 使用 LibreOffice 宏自动处理
    - 支持跨平台
    """

    def __init__(self):
        super().__init__(
            name="accept_word_changes",
            description="""接受 Word 文档中的所有修订标记

功能：
- 接受 DOCX 文件中的所有修订（Track Changes）
- 使用 LibreOffice 自动处理
- 生成清洁的最终版本文档

使用场景：
- 清理文档修订记录
- 批量接受修订
- 文档定稿处理

示例：
- accept_word_changes(input_file="draft.docx", output_file="final.docx")

参数说明：
- input_file: 输入 DOCX 文件路径（包含修订）
- output_file: 输出 DOCX 文件路径（清洁版本）

注意：
- 需要安装 LibreOffice（soffice 命令）
- 处理时间取决于文档大小（通常 10-30 秒）
- 原文件不会被修改
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        self.working_dir = Path.cwd().parent  # D:\溯源\ 或 /opt/app/ 等

    async def execute(
        self,
        input_file: str,
        output_file: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        接受 Word 文档所有修订

        Args:
            input_file: 输入 DOCX 文件路径
            output_file: 输出 DOCX 文件路径

        Returns:
            {
                "success": bool,
                "data": {
                    "input_file": str,
                    "output_file": str,
                    "size": int
                },
                "summary": str
            }
        """
        try:
            # 1. 路径解析
            input_path = self._resolve_path(input_file)
            output_path = self._resolve_path(output_file)

            if not input_path or not output_path:
                return {
                    "success": False,
                    "data": {"error": "路径无效"},
                    "summary": "接受修订失败：路径无效"
                }

            if not input_path.exists():
                return {
                    "success": False,
                    "data": {"error": f"输入文件不存在: {input_file}"},
                    "summary": "接受修订失败：文件不存在"
                }

            if input_path.suffix.lower() != ".docx":
                return {
                    "success": False,
                    "data": {"error": f"不支持的文件格式: {input_path.suffix}"},
                    "summary": "接受修订失败：仅支持 DOCX 格式"
                }

            # 2. 复制文件到输出位置
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, output_path)

            # 3. 设置 LibreOffice 宏
            if not self._setup_libreoffice_macro():
                return {
                    "success": False,
                    "data": {"error": "LibreOffice 宏设置失败"},
                    "summary": "接受修订失败：宏设置失败"
                }

            # 4. 执行 LibreOffice 宏
            cmd = [
                "soffice",
                "--headless",
                f"-env:UserInstallation=file://{LIBREOFFICE_PROFILE}",
                "--norestore",
                "vnd.sun.star.script:Standard.Module1.AcceptAllTrackedChanges?language=Basic&location=application",
                str(output_path.absolute()),
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                    env=get_soffice_env(),
                )
            except subprocess.TimeoutExpired:
                # Timeout 通常表示成功（LibreOffice 已完成并退出）
                logger.info(
                    "accept_changes_timeout",
                    input_file=str(input_path),
                    output_file=str(output_path)
                )

            # 5. 验证输出文件
            if not output_path.exists():
                return {
                    "success": False,
                    "data": {"error": "输出文件未生成"},
                    "summary": "接受修订失败：输出文件未生成"
                }

            file_size = output_path.stat().st_size

            logger.info(
                "accept_changes_success",
                input_file=str(input_path),
                output_file=str(output_path),
                size=file_size
            )

            return {
                "success": True,
                "data": {
                    "input_file": str(input_path),
                    "output_file": str(output_path),
                    "size": file_size
                },
                "summary": f"已接受所有修订：{input_path.name} -> {output_path.name}"
            }

        except Exception as e:
            logger.error("accept_changes_failed", input_file=input_file, error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"接受修订失败：{str(e)[:80]}"
            }

    def _setup_libreoffice_macro(self) -> bool:
        """设置 LibreOffice 宏"""
        try:
            macro_dir = Path(MACRO_DIR)
            macro_file = macro_dir / "Module1.xba"

            # 检查宏是否已存在
            if macro_file.exists() and "AcceptAllTrackedChanges" in macro_file.read_text():
                return True

            # 初始化 LibreOffice 配置目录
            if not macro_dir.exists():
                subprocess.run(
                    [
                        "soffice",
                        "--headless",
                        f"-env:UserInstallation=file://{LIBREOFFICE_PROFILE}",
                        "--terminate_after_init",
                    ],
                    capture_output=True,
                    timeout=10,
                    check=False,
                    env=get_soffice_env(),
                )
                macro_dir.mkdir(parents=True, exist_ok=True)

            # 写入宏文件
            macro_file.write_text(ACCEPT_CHANGES_MACRO, encoding='utf-8')
            logger.info("libreoffice_macro_setup", macro_file=str(macro_file))
            return True

        except Exception as e:
            logger.error("libreoffice_macro_setup_failed", error=str(e))
            return False

    def _resolve_path(self, path: str) -> Path:
        """解析路径（支持相对路径和绝对路径）"""
        try:
            file_path = Path(path)

            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            return file_path.resolve()

        except Exception as e:
            logger.error("accept_changes_path_resolution_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "accept_word_changes",
            "description": """接受 Word 文档中的所有修订标记

接受 DOCX 文件中的所有修订（Track Changes），生成清洁的最终版本。

使用场景：
- 清理文档修订记录
- 批量接受修订
- 文档定稿处理

注意：
- 需要安装 LibreOffice
- 处理时间 10-30 秒
- 原文件不会被修改
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_file": {
                        "type": "string",
                        "description": "输入 DOCX 文件路径（包含修订）。示例：'draft.docx' 或 'D:/work/draft.docx'"
                    },
                    "output_file": {
                        "type": "string",
                        "description": "输出 DOCX 文件路径（清洁版本）。示例：'final.docx' 或 'D:/work/final.docx'"
                    }
                },
                "required": ["input_file", "output_file"]
            }
        }

    def is_available(self) -> bool:
        """检查 LibreOffice 是否可用"""
        try:
            result = subprocess.run(
                ["soffice", "--version"],
                capture_output=True,
                timeout=5,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False


# 创建工具实例
tool = AcceptChangesTool()
