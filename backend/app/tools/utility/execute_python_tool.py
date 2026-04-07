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
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List
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

        # ✅ 图表文件存储目录
        self.CHARTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend_data_registry", "charts")
        self.CHARTS_DIR = os.path.abspath(self.CHARTS_DIR)

        # 确保永久目录和图表目录存在
        os.makedirs(self.PERMANENT_DIR, exist_ok=True)
        os.makedirs(self.CHARTS_DIR, exist_ok=True)

        super().__init__(
            name="execute_python",
            description=f"""执行 Python 代码（用于生成文档、数据处理、可视化）

重要说明：
- 当前工作目录：{self.PERMANENT_DIR}
- 图表保存目录：{self.CHARTS_DIR}
- 生成文件时请使用相对路径（如：'report.docx'），不要使用绝对路径（如：/root/xxx.docx）
- 工具会自动将生成的文件保存到永久目录，并返回完整路径
- 支持 python-docx, matplotlib, pandas 等所有 Python 库
- 超时时间：30秒（可调整）

中文字体设置（matplotlib图表）：
```python
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

# ✅ 推荐方法：直接指定字体文件（最稳定）
chinese_font = FontProperties(fname='/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc')
fig, ax = plt.subplots()
ax.set_title('中文标题', fontproperties=chinese_font)
ax.set_xlabel('横轴', fontproperties=chinese_font)
ax.set_ylabel('纵轴', fontproperties=chinese_font)
```

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
            version="1.0.2",
            requires_context=False
        )

        # 记录是否使用 IPython
        self.use_ipython = HAS_IPYTHON
        self.default_timeout = 30
        self.max_output_size = 1024 * 1024  # 1MB

        logger.info(
            "execute_python_tool_initialized",
            use_ipython=self.use_ipython,
            permanent_dir=self.PERMANENT_DIR,
            charts_dir=self.CHARTS_DIR,
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
                "status": "failed",  # ✅ 添加 status 字段
                "success": False,
                "error": "Missing required parameter: code",
                "data": None,
                "metadata": {
                    "tool_name": "execute_python",
                    "error_type": "MISSING_PARAMETER"
                },
                "summary": "缺少代码参数"
            }

        # ✅ 确保图表目录存在（每次执行时都检查）
        os.makedirs(self.CHARTS_DIR, exist_ok=True)

        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="python_exec_")
        original_dir = os.getcwd()

        # 获取 backend 目录（用于相对路径访问数据文件）
        # ✅ 修复：从 execute_python_tool.py 往上 3 级到达 backend/ 目录
        # 文件位置：backend/app/tools/utility/execute_python_tool.py
        # 需要到达：backend/
        backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..")
        backend_dir = os.path.abspath(backend_dir)

        try:
            # 根据是否安装 IPython 选择执行方式
            if self.use_ipython:
                # ⚠️ 在 backend 目录执行代码，以便相对路径能找到数据文件
                os.chdir(backend_dir)

                # ✅ 自动注册中文字体（避免用户代码中字体设置错误）
                original_code = code
                code = self._inject_chinese_font_support(code)

                logger.info(
                    "chinese_font_injection",
                    original_code_length=len(original_code),
                    injected_code_length=len(code),
                    code_modified=(code != original_code),
                    has_matplotlib_import='import matplotlib' in original_code or 'from matplotlib' in original_code,
                    has_chinese_font_setup='FontProperties' in original_code or 'font.sans-serif' in original_code or 'Noto' in original_code
                )

                result = await self._execute_with_ipython(code, timeout or self.default_timeout)
                # 切回临时目录，用于查找生成的文件
                os.chdir(temp_dir)
            else:
                # subprocess 模式：在临时目录执行
                os.chdir(temp_dir)

                # ✅ 自动注册中文字体
                original_code = code
                code = self._inject_chinese_font_support(code)

                logger.info(
                    "chinese_font_injection",
                    original_code_length=len(original_code),
                    injected_code_length=len(code),
                    code_modified=(code != original_code),
                    mode="subprocess"
                )

                result = await self._execute_with_subprocess(code, timeout or self.default_timeout)

            # ✅ 从 output 中提取用户保存的文件路径（绝对路径保存的文件）
            output = result["data"].get("output", "")
            user_saved_files = self._extract_file_paths_from_output(output)

            # ✅ 查找临时目录生成的文件（相对路径保存的文件）
            temp_files = self._find_generated_files(temp_dir)

            logger.info(
                "execute_python_file_detection",
                temp_files_count=len(temp_files),
                user_saved_files_count=len(user_saved_files),
                user_saved_files=user_saved_files
            )

            # 移动临时文件到永久目录
            moved_temp_files = self._move_to_permanent_dir(temp_files)

            # 合并文件列表（移动的临时文件 + 用户保存的文件）
            final_files = moved_temp_files + user_saved_files

            result["data"]["files"] = final_files
            result["data"]["engine"] = "ipython" if self.use_ipython else "subprocess"

            # ✅ 处理办公文件：生成 PDF 预览（与 Office 工具统一格式）
            office_extensions = {'.docx', '.xlsx', '.pptx', '.pdf', '.doc', '.xls', '.ppt'}
            office_files = [f for f in final_files if Path(f).suffix.lower() in office_extensions]

            if office_files:
                # 只处理第一个 office 文件（与 Office 工具行为一致）
                office_file = office_files[0]
                try:
                    from app.services.pdf_converter import pdf_converter
                    pdf_preview = await pdf_converter.convert_to_pdf(office_file)
                    result["data"]["pdf_preview"] = pdf_preview
                    result["data"]["file_path"] = office_file
                    # ✅ 只在执行成功时覆盖 summary
                    if result.get("success", False):
                        result["summary"] = f"✅ 工具已执行完成，生成文档：{Path(office_file).name}"
                    logger.info(
                        "execute_python_pdf_generated",
                        pdf_id=pdf_preview["pdf_id"],
                        office_file=office_file,
                        execution_success=result.get("success", False)
                    )
                except Exception as pdf_error:
                    logger.warning("execute_python_pdf_conversion_failed", error=str(pdf_error))
                    # PDF 转换失败时，仍然返回文件信息
                    result["data"]["file_path"] = office_file
                    # ✅ 只在执行成功时覆盖 summary
                    if result.get("success", False):
                        result["summary"] = f"✅ 工具已执行完成，生成文件：{Path(office_file).name}"
            elif final_files:
                # ✅ 只在执行成功时覆盖 summary
                if result.get("success", False):
                    file_names = [Path(f).name for f in final_files]
                    result["summary"] = f"✅ 工具已执行完成，生成文件: {', '.join(file_names)}"
            else:
                # ✅ 只在执行成功时覆盖 summary
                if result.get("success", False):
                    result["summary"] = "✅ 工具已执行完成，计算任务已完成"

            # ✅ 检测图表输出（CHART_SAVED:xxx.png）
            chart_paths = self._extract_chart_paths(result["data"].get("output", ""))

            # ✅ 新增：检测 ECharts 标准格式 JSON 输出
            echarts_data = self._extract_echarts_format(result["data"].get("output", ""))

            logger.info(
                "chart_paths_extracted",
                chart_paths=chart_paths,
                echarts_found=echarts_data is not None,
                output_preview=result["data"].get("output", "")[:200]
            )

            # 如果检测到图表，自动缓存到 ImageCache
            if chart_paths:
                from app.services.image_cache import ImageCache
                image_cache = ImageCache()

                for chart_path in chart_paths:
                    # ✅ 修复：将相对路径转换为绝对路径（因为工作目录已切换到temp_dir）
                    # Python代码在backend_dir执行，所以相对路径需要基于backend_dir解析
                    if not os.path.isabs(chart_path):
                        abs_chart_path = os.path.abspath(os.path.join(backend_dir, chart_path))
                    else:
                        abs_chart_path = chart_path

                    logger.info(
                        "checking_chart_file",
                        relative_path=chart_path,
                        absolute_path=abs_chart_path,
                        exists=os.path.exists(abs_chart_path)
                    )

                    # 检查文件是否存在（使用绝对路径）
                    if os.path.exists(abs_chart_path):
                        try:
                            logger.info(
                                "chart_file_found",
                                chart_path=chart_path,
                                abs_chart_path=abs_chart_path,
                                file_size=os.path.getsize(abs_chart_path)
                            )

                            with open(abs_chart_path, 'rb') as f:
                                base64_data = base64.b64encode(f.read()).decode('utf-8')

                            # 生成唯一的 chart_id（使用纳秒时间戳避免冲突）
                            chart_id = f"matplotlib_{time.time_ns()}"

                            logger.info(
                                "saving_to_image_cache",
                                chart_id=chart_id,
                                cache_dir=image_cache.cache_dir
                            )

                            image_info = image_cache.save(
                                base64_data=base64_data,
                                chart_id=chart_id
                            )

                            logger.info(
                                "chart_cached",
                                chart_path=chart_path,
                                image_url=image_info["url"],
                                image_id=image_info["image_id"],
                                local_path=image_info["local_path"]
                            )

                            # ✅ 添加到 visuals 字段（顶层，前端渲染使用）
                            result.setdefault("visuals", []).append({
                                "id": chart_id,
                                "type": "image",
                                "title": f"图表 {Path(chart_path).stem}",
                                "data": {
                                    "url": image_info["url"],
                                    "image_id": image_info["image_id"]
                                },
                                "meta": {
                                    "generator": "execute_python",
                                    "schema_version": "3.1",
                                    "file_path": abs_chart_path
                                }
                            })

                            # 更新摘要
                            result["summary"] = f"✅ 工具已执行完成，图表生成成功：![Chart]({image_info['url']})"

                        except Exception as e:
                            logger.error(
                                "chart_cache_failed",
                                chart_path=chart_path,
                                abs_chart_path=abs_chart_path,
                                error=str(e),
                                error_type=type(e).__name__,
                                exc_info=True
                            )
                            # ⚠️ 缓存失败时，仍返回文件路径供调试
                            result.setdefault("visuals", []).append({
                                "id": chart_id,
                                "type": "image",
                                "title": f"图表 {Path(chart_path).stem}",
                                "data": {
                                    "url": None,
                                    "file_path": abs_chart_path,
                                    "error": str(e)
                                },
                                "meta": {
                                    "generator": "execute_python",
                                    "schema_version": "3.1",
                                    "cache_failed": True
                                }
                            })
                            result["summary"] = f"✅ 工具已执行完成，图表生成成功（缓存失败）：{abs_chart_path}"

            # ✅ 新增：处理 ECharts 标准格式 JSON 数据
            if echarts_data:
                try:
                    # 检测图表类型
                    if "series" in echarts_data:
                        series_list = echarts_data["series"]
                        if isinstance(series_list, list) and len(series_list) > 0:
                            first_series = series_list[0]
                            chart_type = first_series.get("type", "chart").lower()  # 统一转换为小写
                        else:
                            chart_type = "chart"
                    else:
                        chart_type = "chart"

                    # ✅ 从ECharts配置中提取display title
                    echarts_title = echarts_data.get("title", {})
                    if isinstance(echarts_title, dict):
                        display_title = echarts_title.get("text", f"{chart_type.upper()}图表")
                    else:
                        display_title = echarts_title or f"{chart_type.upper()}图表"

                    # ✅ 直接使用 ECharts 标准格式
                    result.setdefault("visuals", []).append({
                        "id": f"echarts_{time.time_ns()}",
                        "type": chart_type,
                        "title": display_title,
                        "data": echarts_data,  # 直接使用ECharts格式（包含完整title、yAxis.name等）
                        "meta": {
                            "generator": "execute_python",
                            "schema_version": "echarts_standard"
                        }
                    })
                    logger.info(
                        "echarts_format_added",
                        chart_type=chart_type,
                        display_title=display_title,
                        has_title_text="title" in echarts_data,
                        data_format=list(echarts_data.keys()) if isinstance(echarts_data, dict) else type(echarts_data).__name__
                    )
                    # 更新摘要
                    if not chart_paths:  # 如果没有matplotlib图表，使用ECharts摘要
                        result["summary"] = f"✅ 工具已执行完成，ECharts图表生成成功：{display_title}"
                except Exception as e:
                    logger.warning(
                        "echarts_processing_failed",
                        error=str(e),
                        echarts_data=echarts_data
                    )

            return result

        except Exception as e:
            logger.error("execute_python_failed", error=str(e), exc_info=True)
            return {
                "status": "failed",  # ✅ 添加 status 字段
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
                "status": "failed",  # ✅ 添加 status 字段
                "success": False,
                "data": {"error": "执行超时"},
                "summary": "执行超时"
            }

        if execution_result["error"]:
            return {
                "status": "failed",  # ✅ 添加 status 字段
                "success": False,
                "data": {"error": str(execution_result["error"])},
                "summary": "执行失败"
            }

        result = execution_result["result"]

        if result.error_in_exec:
            return {
                "status": "failed",  # ✅ 添加 status 字段
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
            "status": "success",  # ✅ 添加 status 字段
            "success": True,
            "data": {"output": output},
            "summary": "✅ 工具已执行完成，计算任务已完成"
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
                "status": "success" if result.returncode == 0 else "failed",  # ✅ 添加 status 字段
                "success": result.returncode == 0,
                "data": {"output": output},
                "summary": "✅ 工具已执行完成，计算任务已完成" if result.returncode == 0 else "执行失败"
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "failed",  # ✅ 添加 status 字段
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

    def _extract_chart_paths(self, output: str) -> list:
        """
        从 Python 代码输出中提取图表路径

        检测格式：CHART_SAVED:/path/to/chart.png

        Args:
            output: Python 代码输出

        Returns:
            图表路径列表
        """
        chart_paths = []
        output_lines = output.split('\n')

        for line in output_lines:
            line = line.strip()
            if line.startswith("CHART_SAVED:"):
                chart_path = line.split("CHART_SAVED:")[1].strip()
                chart_paths.append(chart_path)

        return chart_paths

    def _extract_echarts_format(self, output: str) -> dict:
        """
        从 Python 代码输出中提取 ECharts 标准格式 JSON 数据

        检测格式：JSON字符串包含 series 字段（ECharts标准格式）
        可能包含：xAxis, yAxis, series, tooltip, legend 等字段

        Args:
            output: Python 代码输出

        Returns:
            ECharts 配置字典，如果未找到则返回 None
        """
        import json
        import re

        output_lines = output.split('\n')

        for line in output_lines:
            line = line.strip()
            if not line:
                continue

            try:
                # 尝试解析 JSON
                chart_data = json.loads(line)

                # 验证是否为 ECharts 标准格式（必须有 series 字段）
                if isinstance(chart_data, dict) and "series" in chart_data:
                    # series 必须是数组类型
                    if isinstance(chart_data["series"], list):
                        logger.info(
                            "echarts_format_detected",
                            chart_type=chart_data.get("series", [{}])[0].get("type", "unknown") if len(chart_data.get("series", [])) > 0 else "unknown",
                            has_xAxis="xAxis" in chart_data,
                            has_yAxis="yAxis" in chart_data,
                            series_count=len(chart_data.get("series", []))
                        )
                        return chart_data
            except (json.JSONDecodeError, ValueError):
                # 不是有效的 JSON，继续下一行
                continue

        return None

    def _inject_chinese_font_support(self, code: str) -> str:
        """
        自动注入中文字体支持代码

        策略：在代码开头注册字体，并替换用户错误的字体设置
        """
        # 检测是否使用了matplotlib
        has_matplotlib_import = any([
            'import matplotlib' in code,
            'from matplotlib' in code,
        ])

        if not has_matplotlib_import:
            logger.debug("font_injection_skipped", reason="no matplotlib import")
            return code

        logger.info("font_injection_started", has_matplotlib_import=has_matplotlib_import)

        # 步骤1：在代码开头注册字体文件并设置为默认字体
        font_registration_code = """# ===== 自动注入中文字体支持 =====
from matplotlib import font_manager
import matplotlib.pyplot as plt
import os
_font_path = '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'
if os.path.exists(_font_path):
    try:
        font_manager.fontManager.addfont(_font_path)
        # 获取字体名称并设置为默认
        _font_prop = font_manager.FontProperties(fname=_font_path)
        _font_name = _font_prop.get_name()
        plt.rcParams['font.family'] = _font_name
        plt.rcParams['axes.unicode_minus'] = False
    except Exception:
        pass
# ===== 字体注册完成 =====

"""

        lines = code.split('\n')
        modified_lines = [font_registration_code]

        # 步骤2：处理每一行，删除错误的字体设置
        for line in lines:
            # 检测并删除错误的字体设置（已在注册代码中统一配置）
            if "plt.rcParams['font.sans-serif']" in line or "plt.rcParams['axes.unicode_minus']" in line:
                logger.debug("font_setting_removed", original_line=line.strip())
                continue  # 跳过这行，不添加到结果中
            else:
                modified_lines.append(line)

        injected_code = '\n'.join(modified_lines)

        logger.info(
            "font_injection_completed",
            original_length=len(code),
            injected_length=len(injected_code),
            injection_type="replace_font_settings"
        )

        return injected_code

    def _extract_file_paths_from_output(self, output: str) -> List[str]:
        """
        从 Python 代码输出中提取文件路径

        检测常见的文件保存输出格式：
        - "报告已生成：/path/to/file.docx"
        - "文件已保存：/path/to/file.xlsx"
        - "File saved: /path/to/file.pdf"
        - "/path/to/file.docx"

        Args:
            output: Python 代码输出

        Returns:
            文件路径列表
        """
        import re
        file_paths = []

        if not output:
            return file_paths

        # 常见的文件保存模式
        patterns = [
            r'(?:报告已生成|文件已保存|已生成|保存成功|File saved|saved)[:：]\s*([/\w\-.]+\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt))',
            r'([/\w\-.]+\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt))\s*[已]*[保存生成]*',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, output)
            file_paths.extend(matches)

        # 去重并验证文件存在
        unique_paths = []
        seen = set()
        for path in file_paths:
            # 规范化路径
            path = os.path.abspath(path) if not os.path.isabs(path) else path
            if path not in seen and os.path.exists(path):
                unique_paths.append(path)
                seen.add(path)

        return unique_paths

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
                "【中文字体设置】matplotlib图表中文显示（重要）：\n"
                "```python\n"
                "import matplotlib\n"
                "matplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "from matplotlib.font_manager import FontProperties\n\n"
                "# ✅ 推荐方法：直接指定字体文件（最稳定）\n"
                "chinese_font = FontProperties(fname='/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc')\n"
                "fig, ax = plt.subplots()\n"
                "ax.set_title('中文标题', fontproperties=chinese_font)\n"
                "ax.set_xlabel('横轴', fontproperties=chinese_font)\n"
                "ax.set_ylabel('纵轴', fontproperties=chinese_font)\n"
                "```\n\n"
                "文件路径（重要）：\n"
                "• 所有生成的文件应保存到项目目录下的绝对路径\n"
                "• 报告文件：/home/xckj/suyuan/backend_data_registry/report.docx\n"
                "• 例如：doc.save('/home/xckj/suyuan/backend_data_registry/report.docx')\n"
                "• 工具会自动检测 backend_data_registry 目录中新增的文件\n"
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
