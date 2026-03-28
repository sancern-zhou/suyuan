"""
Execute Python Code Tool

执行 Python 代码工具（用于文档生成、数据处理、可视化）

特性：
- 在隔离的临时目录中执行代码
- 30 秒超时保护（可配置）
- 使用 IPython 自动捕获输出（stdout/stderr/display）
- 返回生成的文件列表
- 自动清理临时文件
- 支持所有 Python 库（python-docx, matplotlib, pandas 等）
- 支持魔法命令（%time, %matplotlib inline 等）
- 如果 IPython 不可用，自动回退到 subprocess 方案

安全措施：
1. 临时目录隔离
2. 超时保护
3. 输出截断（1MB 限制）
"""

import tempfile
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

# 尝试导入 IPython
try:
    from IPython.terminal.interactiveshell import TerminalInteractiveShell
    HAS_IPYTHON = True
except ImportError:
    HAS_IPYTHON = False

logger = structlog.get_logger()


class ExecutePythonTool(LLMTool):
    """
    Python 代码执行工具

    参考：
    - KIMI ipython 工具
    - openwork-dev: Python 执行环境
    """

    def __init__(self):
        # 永久文件存储目录（使用项目目录）
        self.PERMANENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend_data_registry", "python_generated_files")
        self.PERMANENT_DIR = os.path.abspath(self.PERMANENT_DIR)

        # 确保永久目录存在
        os.makedirs(self.PERMANENT_DIR, exist_ok=True)

        super().__init__(
            name="execute_python",
            description=f"""执行 Python 代码（用于生成文档、数据处理、可视化）

重要说明：
- 当前工作目录：{self.PERMANENT_DIR}
- 生成文件时请使用相对路径（如：'report.docx'），不要使用绝对路径（如：/root/xxx.docx）
- 工具会自动将生成的文件保存到永久目录，并返回完整路径
- 支持 python-docx, matplotlib, pandas 等所有 Python 库
- 超时时间：30秒（可调整）

示例：
```python
# ✅ 正确：使用相对路径
from docx import Document
doc = Document()
doc.add_paragraph('Hello')
doc.save('report.docx')  # 保存到当前工作目录

# ❌ 错误：使用绝对路径（可能导致权限问题）
doc.save('/root/report.docx')
```""",
            category=ToolCategory.QUERY,
            version="1.0.1",
            requires_context=False
        )

        # 记录是否使用 IPython
        self.use_ipython = HAS_IPYTHON
        self.default_timeout = 30
        self.max_output_size = 1024 * 1024  # 1MB

        # 永久文件存储目录（使用项目目录）
        self.PERMANENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend_data_registry", "python_generated_files")
        self.PERMANENT_DIR = os.path.abspath(self.PERMANENT_DIR)

        # 确保永久目录存在
        os.makedirs(self.PERMANENT_DIR, exist_ok=True)

        logger.info(
            "execute_python_tool_initialized",
            use_ipython=self.use_ipython,
            permanent_dir=self.PERMANENT_DIR,
            timeout=self.default_timeout
        )

    async def execute(
        self,
        context=None,
        code: str = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 Python 代码

        Args:
            code: Python 代码
            timeout: 超时时间（秒），默认 30 秒

        Returns:
            {
                "success": True/False,
                "data": {
                    "output": "代码输出",
                    "files": ["/path/to/generated/file.docx"],
                    "engine": "ipython" or "subprocess"
                },
                "summary": "执行成功"
            }
        """
        if not code:
            return {
                "success": False,
                "error": "Missing required parameter: code",
                "data": None,
                "metadata": {
                    "tool_name": "execute_python",
                    "error_type": "MISSING_PARAMETER"
                },
                "summary": "缺少代码参数"
            }

        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="python_exec_")
        original_dir = os.getcwd()

        try:
            # 切换到临时目录
            os.chdir(temp_dir)

            # 根据是否安装 IPython 选择执行方式
            if self.use_ipython:
                result = await self._execute_with_ipython(code, timeout or self.default_timeout)
            else:
                result = await self._execute_with_subprocess(code, timeout or self.default_timeout)

            # 查找生成的文件
            generated_files = self._find_generated_files(temp_dir)

            # 移动文件到永久目录
            final_files = self._move_to_permanent_dir(generated_files)

            result["data"]["files"] = final_files
            result["data"]["engine"] = "ipython" if self.use_ipython else "subprocess"

            # 如果有文件，添加到摘要
            if final_files:
                file_names = [Path(f).name for f in final_files]
                result["summary"] = f"执行成功，生成文件: {', '.join(file_names)}"
            else:
                result["summary"] = "执行成功"

            return result

        except Exception as e:
            logger.error("execute_python_failed", error=str(e), exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "data": {"error": str(e)},
                "metadata": {
                    "tool_name": "execute_python",
                    "error_type": type(e).__name__
                },
                "summary": f"执行失败: {str(e)}"
            }
        finally:
            # 恢复工作目录
            os.chdir(original_dir)
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _execute_with_ipython(self, code: str, timeout: int) -> Dict[str, Any]:
        """使用 IPython 执行代码"""
        shell = TerminalInteractiveShell()

        # 捕获输出
        outputs = []
        errors = []

        class OutputCapture:
            def __init__(self, outputs_list, errors_list, is_stderr=False):
                self.outputs = outputs_list
                self.errors = errors_list
                self.is_stderr = is_stderr

            def write(self, text):
                if self.is_stderr:
                    self.errors.append(text)
                else:
                    self.outputs.append(text)

            def flush(self):
                pass

        original_stdout = sys.stdout
        original_stderr = sys.stderr

        sys.stdout = OutputCapture(outputs, errors, is_stderr=False)
        sys.stderr = OutputCapture(outputs, errors, is_stderr=True)

        # 设置超时（使用线程）
        execution_result = {"result": None, "error": None}
        timeout_event = threading.Event()

        def run_with_timeout():
            try:
                execution_result["result"] = shell.run_cell(
                    code,
                    silent=False,
                    store_history=False
                )
            except Exception as e:
                execution_result["error"] = e
            finally:
                timeout_event.set()

        thread = threading.Thread(target=run_with_timeout)
        thread.daemon = True
        thread.start()

        # 等待执行完成或超时
        thread.join(timeout=timeout)

        # 恢复原始输出流
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        if thread.is_alive():
            # 超时
            return {
                "success": False,
                "data": {"error": "执行超时"},
                "summary": "执行超时"
            }

        if execution_result["error"]:
            return {
                "success": False,
                "data": {"error": str(execution_result["error"])},
                "summary": "执行失败"
            }

        result = execution_result["result"]

        if result.error_in_exec:
            return {
                "success": False,
                "data": {"error": str(result.error_in_exec)},
                "summary": "执行失败"
            }

        # 组合输出
        output = "".join(outputs)
        if errors:
            output += "\n错误输出:\n" + "".join(errors)

        # 如果有返回值，也添加到输出
        if result.result is not None:
            output += str(result.result)

        # 截断输出
        if len(output) > self.max_output_size:
            output = output[:self.max_output_size] + "\n... (输出被截断)"

        return {
            "success": True,
            "data": {"output": output},
            "summary": "执行成功"
        }

    async def _execute_with_subprocess(self, code: str, timeout: int) -> Dict[str, Any]:
        """使用 subprocess 执行代码（回退方案）"""
        # 写入脚本文件
        script_file = os.path.join(os.getcwd(), "script.py")
        with open(script_file, 'w', encoding='utf-8') as f:
            f.write(code)

        # 执行代码
        try:
            result = subprocess.run(
                [sys.executable, script_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd()
            )

            output = result.stdout or ""
            if result.stderr:
                output += f"\n错误输出:\n{result.stderr}"

            # 截断输出
            if len(output) > self.max_output_size:
                output = output[:self.max_output_size] + "\n... (输出被截断)"

            return {
                "success": result.returncode == 0,
                "data": {"output": output},
                "summary": "执行成功" if result.returncode == 0 else "执行失败"
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "data": {"error": "执行超时"},
                "summary": "执行超时"
            }

    def _find_generated_files(self, temp_dir: str) -> list:
        """查找生成的文件（排除临时文件）"""
        generated_files = []
        for root, dirs, files in os.walk(temp_dir):
            # 跳过 __pycache__ 目录
            if '__pycache__' in dirs:
                dirs.remove('__pycache__')

            for file in files:
                # 排除脚本文件和缓存文件
                if file not in ['script.py'] and not file.endswith('.pyc'):
                    file_path = os.path.join(root, file)
                    # 只包含文件，不包含目录
                    if os.path.isfile(file_path):
                        generated_files.append(file_path)
        return generated_files

    def _move_to_permanent_dir(self, files: list) -> list:
        """移动文件到永久目录"""
        final_files = []
        for file_path in files:
            file_name = os.path.basename(file_path)
            permanent_path = os.path.join(self.PERMANENT_DIR, file_name)

            # 如果文件已存在，添加时间戳
            if os.path.exists(permanent_path):
                name, ext = os.path.splitext(file_name)
                permanent_path = os.path.join(
                    self.PERMANENT_DIR,
                    f"{name}_{int(time.time())}{ext}"
                )

            # 使用 shutil.move 代替 os.rename（跨文件系统支持）
            shutil.move(file_path, permanent_path)
            final_files.append(permanent_path)

        return final_files

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "execute_python",
            "description": (
                "【工具名称：execute_python】执行 Python 代码（用于生成文档、数据处理、可视化）。\n\n"
                "使用场景：\n"
                "• 文档生成：使用 python-docx 生成 Word 文档\n"
                "• 数据处理：使用 pandas 处理数据\n"
                "• 数据可视化：使用 matplotlib 生成图表\n"
                "• 数据分析：使用 numpy、scipy 进行科学计算\n\n"
                "支持的库：\n"
                "• python-docx: Word 文档生成\n"
                "• matplotlib: 图表生成\n"
                "• pandas: 数据处理\n"
                "• numpy: 数值计算\n"
                "• openpyxl: Excel 文件处理\n\n"
                "文件路径（重要）：\n"
                "• 所有生成的文件应保存到项目目录下的绝对路径\n"
                "• 报告文件：/home/xckj/suyuan/backend_data_registry/report.docx\n"
                "• 例如：doc.save('/home/xckj/suyuan/backend_data_registry/report.docx')\n"
                "• 注意：使用实际路径保存文件时，工具返回的 files 列表可能为空，但文件确实会生成\n"
                "• 建议在代码中打印文件保存路径，以便确认文件生成位置\n\n"
                "安全限制：\n"
                "• 临时目录隔离执行\n"
                "• 默认超时 30 秒\n"
                "• 输出限制 1MB\n\n"
                "【重要提示】\n"
                "• 工具名称必须是 'execute_python'，不要使用 run_python、exec_python 等其他名称\n"
                "• 文件必须保存到项目目录内的绝对路径，例如 /home/xckj/suyuan/backend_data_registry/\n"
                "• matplotlib 需要使用无后端模式：matplotlib.use('Agg')\n\n"
                "示例：\n"
                "```\n"
                "from docx import Document\n"
                "doc = Document()\n"
                "doc.add_heading('报告', 0)\n"
                "doc.save('/home/xckj/suyuan/backend_data_registry/report.docx')\n"
                "```"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 Python 代码"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒），默认 30"
                    }
                },
                "required": ["code"]
            }
        }
