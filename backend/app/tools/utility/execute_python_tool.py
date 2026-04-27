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
- 支持 python-docx, matplotlib, pandas, openpyxl 等所有 Python 库
- 超时时间：30秒（可调整）

📊 数据访问功能（自动注入）：
当工具检测到 context 时，会自动注入 `get_raw_data(data_id)` 函数：
- `get_raw_data(data_id)`: 根据 data_id 获取原始数据（字典列表格式）

使用示例：
```python
# 直接使用刚才查询返回的 data_id
data = get_raw_data("air_quality_5min:v1:bbf34146...")
print(f"数据点数: {{len(data)}}")

# 提取字段进行分析
wind_dirs = [float(record['wind_direction_10m']) for record in data]
concentrations = [float(record['PM2_5']) for record in data]
```

📈 Excel 处理最佳实践：
使用 pandas 和 openpyxl 标准库（无需自定义辅助函数）：
```python
# 读取 Excel
import pandas as pd
df = pd.read_excel('file.xlsx')  # 第一个工作表
all_sheets = pd.read_excel('file.xlsx', sheet_name=None)  # 所有工作表

# 创建 Excel（使用公式）
from openpyxl import Workbook, load_workbook
wb = Workbook()
ws = wb.active
ws['A1'] = '标题'
ws['B2'] = '=SUM(A1:A10)'  # ✅ 使用公式，不要硬编码计算结果
wb.save('output.xlsx')

# 编辑现有 Excel
wb = load_workbook('existing.xlsx')
ws = wb.active
ws['A1'] = '新值'
wb.save('modified.xlsx')
```

核心原则：
- ✅ 使用标准库（pandas/openpyxl），不要依赖自定义辅助函数
- ✅ 公式优先：使用 Excel 公式（如 '=SUM(A1:A10)'），不要在 Python 中计算后硬编码
- ✅ 详细文档：backend/docs/skills/excel.md

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
            version="1.0.3",
            requires_context=True  # ✅ 需要上下文以支持数据访问功能
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

                # ✅ 注入数据访问上下文（让用户可以通过 data_id 访问数据）
                original_code = code
                code = self._inject_data_context(code, context)

                # ✅ 自动注册中文字体（避免用户代码中字体设置错误）
                code = self._inject_chinese_font_support(code)

                # ✅ 条件性注入 Excel 辅助函数（保留图表和格式）
                code = self._inject_excel_helpers(code)

                logger.info(
                    "code_injection_completed",
                    original_code_length=len(original_code),
                    injected_code_length=len(code),
                    code_modified=(code != original_code),
                    has_matplotlib_import='import matplotlib' in original_code or 'from matplotlib' in original_code,
                    has_chinese_font_setup='FontProperties' in original_code or 'font.sans-serif' in original_code or 'Noto' in original_code,
                    has_excel_usage='openpyxl' in original_code or 'pandas' in original_code and 'read_excel' in original_code or '.xlsx' in original_code,
                    has_context=context is not None,
                    available_data_count=len(context.available_data_ids) if context and hasattr(context, 'available_data_ids') else 0
                )

                result = await self._execute_with_ipython(code, timeout or self.default_timeout)
                # 切回临时目录，用于查找生成的文件
                os.chdir(temp_dir)
            else:
                # subprocess 模式：在临时目录执行
                os.chdir(temp_dir)

                # ✅ 注入数据访问上下文（让用户可以通过 data_id 访问数据）
                original_code = code
                code = self._inject_data_context(code, context)

                # ✅ 自动注册中文字体
                code = self._inject_chinese_font_support(code)

                # ✅ 条件性注入 Excel 辅助函数（保留图表和格式）
                code = self._inject_excel_helpers(code)

                logger.info(
                    "code_injection_completed",
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

            # ✅ 处理 Notebook 文件：生成 HTML 预览
            notebook_files = [f for f in final_files if f.endswith('.ipynb')]

            if notebook_files and "file_path" not in result["data"]:
                # 只处理第一个 notebook 文件
                notebook_file = notebook_files[0]
                try:
                    from app.services.notebook_converter import notebook_converter
                    html_preview = await notebook_converter.convert_to_html(notebook_file)
                    result["data"]["html_preview"] = html_preview
                    result["data"]["file_path"] = notebook_file
                    result["data"]["file_type"] = "notebook"
                    # ✅ 只在执行成功时覆盖 summary
                    if result.get("success", False):
                        result["summary"] = f"✅ 工具已执行完成，生成Notebook：{Path(notebook_file).name}"
                    logger.info(
                        "execute_python_notebook_html_generated",
                        html_id=html_preview["html_id"],
                        notebook_file=notebook_file,
                        execution_success=result.get("success", False)
                    )
                except Exception as html_error:
                    logger.warning("execute_python_notebook_conversion_failed", error=str(html_error))
                    # HTML 转换失败时，仍然返回文件信息
                    result["data"]["file_path"] = notebook_file
                    result["data"]["file_type"] = "notebook"
                    # ✅ 只在执行成功时覆盖 summary
                    if result.get("success", False):
                        result["summary"] = f"✅ 工具已执行完成，生成Notebook：{Path(notebook_file).name}"
            elif final_files and "file_path" not in result["data"]:
                # ✅ 只在执行成功时覆盖 summary
                if result.get("success", False):
                    file_names = [Path(f).name for f in final_files]
                    result["summary"] = f"✅ 工具已执行完成，生成文件: {', '.join(file_names)}"
            else:
                # ✅ 只在执行成功时覆盖 summary
                if result.get("success", False):
                    result["summary"] = "✅ 工具已执行完成，计算任务已完成"

            # ✅ 检测图表输出（CHART_SAVED:xxx.png 或 CHART_SAVED:data:image/png;base64,...）
            chart_data = self._extract_chart_paths(result["data"].get("output", ""))

            # ✅ 新增：检测 ECharts 标准格式 JSON 输出
            echarts_data = self._extract_echarts_format(result["data"].get("output", ""))

            logger.info(
                "chart_paths_extracted",
                chart_paths=chart_data.get("paths", []),
                base64_count=len(chart_data.get("base64_data", [])),
                echarts_found=echarts_data is not None,
                output_preview=result["data"].get("output", "")[:200]
            )

            # 如果检测到图表，自动缓存到 ImageCache
            if chart_data.get("paths") or chart_data.get("base64_data"):
                from app.services.image_cache import ImageCache
                image_cache = ImageCache()

                # 处理文件路径格式的图表
                for chart_path in chart_data.get("paths", []):
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

                # 处理 base64 格式的图表
                for base64_data_url in chart_data.get("base64_data", []):
                    try:
                        # 解析 data:image/png;base64,... 格式
                        if "," in base64_data_url:
                            mime_type, base64_data = base64_data_url.split(",", 1)

                            # 生成唯一的 chart_id
                            chart_id = f"matplotlib_{time.time_ns()}"

                            logger.info(
                                "saving_base64_to_image_cache",
                                chart_id=chart_id,
                                mime_type=mime_type,
                                cache_dir=image_cache.cache_dir
                            )

                            image_info = image_cache.save(
                                base64_data=base64_data,
                                chart_id=chart_id
                            )

                            logger.info(
                                "base64_chart_cached",
                                chart_id=chart_id,
                                image_url=image_info["url"],
                                image_id=image_info["image_id"]
                            )

                            # ✅ 添加到 visuals 字段
                            result.setdefault("visuals", []).append({
                                "id": chart_id,
                                "type": "image",
                                "title": f"图表 {chart_id}",
                                "data": {
                                    "url": image_info["url"],
                                    "image_id": image_info["image_id"]
                                },
                                "meta": {
                                    "generator": "execute_python",
                                    "schema_version": "3.1",
                                    "source": "base64_output"
                                }
                            })

                            # 更新摘要
                            result["summary"] = f"✅ 工具已执行完成，图表生成成功：![Chart]({image_info['url']})"

                            # ✅ 从输出中移除 base64 字符串（太长，LLM不需要）
                            output = result["data"].get("output", "")
                            output = output.replace(base64_data_url, "[图表已生成，详见visuals字段]")
                            result["data"]["output"] = output

                    except Exception as e:
                        logger.error(
                            "base64_chart_cache_failed",
                            error=str(e),
                            error_type=type(e).__name__,
                            exc_info=True
                        )
                        result["summary"] = "✅ 工具已执行完成，图表生成成功（缓存失败）"

            # ✅ 新增：处理 ECharts 标准格式 JSON 数据
            if echarts_data:
                try:
                    # 检测图表类型
                    if "series" in echarts_data:
                        series_list = echarts_data["series"]
                        if isinstance(series_list, list) and len(series_list) > 0:
                            first_series = series_list[0]
                            series_type = first_series.get("type", "chart").lower()

                            # ✅ 检测极坐标图表（风向玫瑰图）
                            if first_series.get("coordinateSystem") == "polar":
                                chart_type = f"polar_{series_type}"
                            else:
                                chart_type = series_type
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
            error_info = self._format_python_error(execution_result["error"], code)
            return {
                "status": "failed",  # ✅ 添加 status 字段
                "success": False,
                "data": {"error": error_info["error_message"], "error_details": error_info},
                "summary": error_info["summary"]
            }

        result = execution_result["result"]

        if result.error_in_exec:
            error_info = self._format_python_error(result.error_in_exec, code)
            return {
                "status": "failed",  # ✅ 添加 status 字段
                "success": False,
                "data": {"error": error_info["error_message"], "error_details": error_info},
                "summary": error_info["summary"]
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

            # 如果执行失败，尝试解析错误信息
            if result.returncode != 0:
                error_info = self._parse_subprocess_error(result.stderr, code)
                return {
                    "status": "failed",
                    "success": False,
                    "data": {"error": error_info["error_message"], "error_details": error_info, "output": output},
                    "summary": error_info["summary"]
                }

            return {
                "status": "success",
                "success": True,
                "data": {"output": output},
                "summary": "✅ 工具已执行完成，计算任务已完成"
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
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

    def _extract_chart_paths(self, output: str) -> dict:
        """
        从 Python 代码输出中提取图表路径和base64数据

        检测格式：
        1. CHART_SAVED:/path/to/chart.png (文件路径)
        2. CHART_SAVED:data:image/png;base64,... (base64数据)

        Args:
            output: Python 代码输出

        Returns:
            {"paths": [文件路径列表], "base64_data": [base64数据列表]}
        """
        result = {"paths": [], "base64_data": []}
        output_lines = output.split('\n')

        for line in output_lines:
            line = line.strip()
            if line.startswith("CHART_SAVED:"):
                chart_data = line.split("CHART_SAVED:")[1].strip()

                # 判断是文件路径还是base64数据
                if chart_data.startswith("data:image/"):
                    # base64格式: data:image/png;base64,...
                    result["base64_data"].append(chart_data)
                else:
                    # 文件路径格式
                    result["paths"].append(chart_data)

        return result

    def _extract_echarts_format(self, output: str) -> dict:
        """
        从 Python 代码输出中提取 ECharts 标准格式 JSON 数据

        检测格式：
        1. 标准格式：JSON字符串包含 series 字段（ECharts标准格式）
        2. 嵌套格式：包含 echarts_option 字段（兼容某些自定义格式）
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

                # ✅ 检测方式1：标准 ECharts 格式（顶层有 series 字段）
                if isinstance(chart_data, dict) and "series" in chart_data:
                    # series 必须是数组类型
                    if isinstance(chart_data["series"], list):
                        logger.info(
                            "echarts_format_detected",
                            format="standard",
                            chart_type=chart_data.get("series", [{}])[0].get("type", "unknown") if len(chart_data.get("series", [])) > 0 else "unknown",
                            has_xAxis="xAxis" in chart_data,
                            has_yAxis="yAxis" in chart_data,
                            series_count=len(chart_data.get("series", []))
                        )
                        return chart_data

                # ✅ 检测方式2：嵌套格式（包含 echarts_option 字段）
                if isinstance(chart_data, dict) and "echarts_option" in chart_data:
                    echarts_option = chart_data["echarts_option"]
                    if isinstance(echarts_option, dict) and "series" in echarts_option:
                        if isinstance(echarts_option["series"], list):
                            logger.info(
                                "echarts_format_detected",
                                format="nested",
                                chart_type=echarts_option.get("series", [{}])[0].get("type", "unknown") if len(echarts_option.get("series", [])) > 0 else "unknown",
                                has_xAxis="xAxis" in echarts_option,
                                has_yAxis="yAxis" in echarts_option,
                                series_count=len(echarts_option.get("series", [])),
                                original_fields=list(chart_data.keys())
                            )
                            # ✅ 直接返回 echarts_option（标准 ECharts 格式）
                            return echarts_option

                # ✅ 检测方式3：嵌套格式（包含 data 字段，data 内有 series）
                if isinstance(chart_data, dict) and "data" in chart_data:
                    inner_data = chart_data["data"]
                    if isinstance(inner_data, dict) and "series" in inner_data:
                        if isinstance(inner_data["series"], list):
                            logger.info(
                                "echarts_format_detected",
                                format="data_nested",
                                chart_type=inner_data.get("series", [{}])[0].get("type", "unknown") if len(inner_data.get("series", [])) > 0 else "unknown",
                                has_xAxis="xAxis" in inner_data,
                                has_yAxis="yAxis" in inner_data,
                                series_count=len(inner_data.get("series", [])),
                                original_fields=list(chart_data.keys())
                            )
                            # ✅ 直接返回 inner_data（标准 ECharts 格式）
                            return inner_data

            except (json.JSONDecodeError, ValueError):
                # 不是有效的 JSON，继续下一行
                continue

        return None

    def _inject_data_context(self, code: str, context) -> str:
        """
        注入数据访问上下文，让用户代码可以通过 data_id 访问数据

        注入内容：
        - get_raw_data(data_id): 获取原始数据（字典列表格式）

        ⚠️ 重要：
        - LLM 应该在代码中直接使用 data_id
        - 不需要从 AVAILABLE_DATA_IDS 列表中选择
        - 系统会根据 data_id 自动定位文件
        """
        # 检查 context 是否存在
        if not context:
            logger.debug("data_context_injection_skipped", reason="no_context")
            return code

        logger.info(
            "data_context_injection_started",
            has_data_manager=context.data_manager is not None
        )

        # 构建注入的代码
        context_injection_code = '''# ===== 数据访问上下文（自动注入） =====
# 获取原始数据（字典列表格式）
def get_raw_data(data_id: str):
    """根据 data_id 获取原始数据（字典列表格式）
    
    Args:
        data_id: 数据ID，格式为 "dataset_name:v1:uuid" 或 "dataset_name_v1_uuid"
    
    Returns:
        数据列表（字典列表）
    """
    import json
    import os
    import sys
    
    # 获取项目根目录（兼容 ipython 环境）
    # 从 sys.path 中查找包含 'backend' 的路径
    backend_root = None
    for path in sys.path:
        if 'backend' in path and os.path.isdir(path):
            # 检查是否是 backend 目录
            test_dir = os.path.join(path, 'backend_data_registry', 'datasets')
            if os.path.isdir(test_dir):
                backend_root = path
                break
    
    # 如果没找到，使用默认路径
    if backend_root is None:
        backend_root = '/home/xckj/suyuan/backend'
    
    datasets_dir = os.path.join(backend_root, 'backend_data_registry', 'datasets')
    
    # 转换 data_id 为文件名
    # 输入: "air_quality_5min:v1:3a61cec54f9a43a2a02e1eebf6cb9b91"
    # 输出: "air_quality_5min_v1_3a61cec54f9a43a2a02e1eebf6cb9b91.json"
    filename = data_id.replace(':', '_') + '.json'
    file_path = os.path.join(datasets_dir, filename)
    
    if not os.path.exists(file_path):
        # 列出可用文件供调试
        try:
            available_files = [f for f in os.listdir(datasets_dir) if f.endswith('.json')][:5]
            raise FileNotFoundError(
                f"数据文件不存在: {file_path}\\n"
                f"可用的数据文件: {available_files}"
            )
        except FileNotFoundError as e:
            raise e
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data

# ===== 数据访问上下文注入完成 =====

'''

        # 在代码开头插入上下文代码
        injected_code = context_injection_code + code

        logger.info(
            "data_context_injection_completed",
            original_length=len(code),
            injected_length=len(injected_code)
        )

        return injected_code

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
        # 使用与 calendar_renderer.py 相同的字体优先级
        font_registration_code = """# ===== 自动注入中文字体支持 =====
from matplotlib import font_manager
import matplotlib.pyplot as plt
import os
from pathlib import Path

# 字体优先级（与 calendar_renderer.py 一致）
_font_configs = [
    # 1. 方正小标宋简体 - 最高优先级
    Path('/home/xckj/.local/share/fonts/方正小标宋简.TTF'),
    # 2. Noto Sans CJK - 系统字体
    Path('/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'),
]

_font_registered = False
for _font_path in _font_configs:
    if _font_path.exists():
        try:
            font_manager.fontManager.addfont(str(_font_path))
            _font_prop = font_manager.FontProperties(fname=str(_font_path))
            _font_name = _font_prop.get_name()
            plt.rcParams['font.family'] = _font_name
            plt.rcParams['axes.unicode_minus'] = False
            _font_registered = True
            break
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

    def _inject_excel_helpers(self, code: str) -> str:
        """
        条件性注入 Excel 辅助函数（仅检测到需要时才注入）

        策略：
        - 检测代码中是否涉及 Excel 操作
        - 检查 openpyxl 是否可用
        - 只在需要时注入辅助函数
        - 自动添加预览触发（即使LLM直接用openpyxl/pandas）
        """
        # 检测是否需要 Excel 操作
        excel_keywords = [
            'edit_excel_data',      # 用户调用辅助函数
            'openpyxl',             # 用户直接用 openpyxl
            '.xlsx',                # 操作 xlsx 文件
            '.xls',                 # 操作 xls 文件
            'to_excel',             # pandas to_excel
            'read_excel',           # pandas read_excel
        ]

        need_excel = any(keyword in code for keyword in excel_keywords)

        if not need_excel:
            logger.debug("excel_injection_skipped", reason="no_excel_keywords")
            return code

        # 检查 openpyxl 是否安装
        try:
            import openpyxl
            openpyxl_available = True
        except ImportError:
            openpyxl_available = False
            logger.warning("excel_injection_skipped", reason="openpyxl_not_installed")

        if not openpyxl_available:
            # openpyxl 未安装，不注入辅助函数
            # 用户代码会直接报错，错误信息更清晰
            return code

        logger.info("excel_injection_started", has_excel_keywords=need_excel)

        # 注入辅助函数
        helper_code = '''# ===== Excel 辅助函数（自动注入，保留图表和格式） =====
def edit_excel_data(file_path, updates, sheet_name=None):
    """
    修改 Excel 数据，保留图表和格式

    ⚠️ 重要：此函数使用 openpyxl 直接修改单元格，不会丢失图表和格式

    Args:
        file_path: Excel 文件路径（.xlsx 格式）
        updates: 更新数据，格式：
            - 单个单元格: {"A1": "新值"}
            - 多个单元格: {"A1": "值1", "B2": "值2", "C3": 123}
        sheet_name: 工作表名（可选，默认使用活动工作表）

    Returns:
        dict: {"success": True, "updated_count": N, "message": "...", "file_path": "..."}

    Example:
        # 修改单个单元格
        edit_excel_data("data.xlsx", {"A1": "北京"})

        # 批量修改
        edit_excel_data("data.xlsx", {
            "A2": "上海",
            "B2": 85,
            "C2": 45
        })
    """
    import openpyxl
    from pathlib import Path
    import os

    try:
        wb = openpyxl.load_workbook(file_path)
        ws = wb[sheet_name] if sheet_name else wb.active

        count = 0
        for cell, value in updates.items():
            ws[cell] = value
            count += 1

        wb.save(file_path)
        wb.close()

        # 规范化文件路径
        file_path = os.path.abspath(file_path)

        # ✅ 打印特殊标记，触发前端预览生成
        print(f"EXCEL_SAVED:{file_path}")

        return {
            "success": True,
            "updated_count": count,
            "message": f"成功更新 {count} 个单元格，图表和格式已保留",
            "file_path": file_path
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"更新失败: {str(e)}"
        }


def read_excel_with_preview(file_path, sheet_name=None, head_rows=20):
    """
    读取 Excel 文件并生成前端预览

    ⚠️ 重要：读取文件也会生成前端预览，方便查看表格内容和格式

    Args:
        file_path: Excel 文件路径（.xlsx 格式）
        sheet_name: 工作表名（可选，默认使用活动工作表）
        head_rows: 读取前几行数据（默认20行）

    Returns:
        dict: {
            "success": True,
            "data": [...],  # 数据列表
            "columns": [...],  # 列名
            "total_rows": N,  # 总行数
            "total_columns": N,  # 总列数
            "file_path": "..."  # 文件路径（触发预览）
        }

    Example:
        # 读取并预览
        result = read_excel_with_preview("data.xlsx")
        print(f"总行数: {result['total_rows']}")
        print(f"数据: {result['data']}")
    """
    import openpyxl
    import pandas as pd
    import os

    try:
        # 规范化文件路径
        file_path = os.path.abspath(file_path)

        # 使用 pandas 读取数据
        df = pd.read_excel(file_path, sheet_name=sheet_name, nrows=head_rows)

        # 使用 openpyxl 获取总行数和列数
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb[sheet_name] if sheet_name else wb.active
        total_rows = ws.max_row
        total_columns = ws.max_column
        wb.close()

        # ✅ 打印特殊标记，触发前端预览生成
        print(f"EXCEL_SAVED:{file_path}")

        return {
            "success": True,
            "data": df.to_dict("records"),
            "columns": df.columns.tolist(),
            "total_rows": total_rows,
            "total_columns": total_columns,
            "preview_rows": len(df),
            "file_path": file_path,
            "message": f"成功读取 Excel 文件，共 {total_rows} 行 x {total_columns} 列"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"读取失败: {str(e)}"
        }


def merge_excel_with_charts(file_paths, output_path):
    """
    合并多个Excel文件到一个工作簿（保留图表、格式、数据）

    方法：
    1. 复制第一个文件作为基础
    2. 逐个复制其他文件的sheet（手动复制：内容+样式+图表）

    ⚠️ 重要：此方法会保留所有图表、格式和数据

    Args:
        file_paths: Excel文件路径列表
        output_path: 输出文件路径

    Returns:
        dict: {"success": True, "merged_count": N, "file_path": "...", "message": "..."}

    Example:
        files = ['/tmp/file1.xlsx', '/tmp/file2.xlsx']
        result = merge_excel_with_charts(files, '/tmp/merged.xlsx')
        # 输出文件包含所有图表和格式
    """
    import openpyxl
    from openpyxl import load_workbook
    import shutil
    import os

    if not file_paths:
        return {
            "success": False,
            "error": "文件列表为空",
            "message": "请提供至少一个Excel文件"
        }

    try:
        # 复制第一个文件作为基础（保留原文件的图表）
        shutil.copy(file_paths[0], output_path)

        # 加载输出文件
        wb_output = load_workbook(output_path)

        merged_count = 0

        # 从第二个文件开始合并
        for file_path in file_paths[1:]:
            if not os.path.exists(file_path):
                continue

            # 加载源文件
            wb_source = load_workbook(file_path)

            for sheet_name in wb_source.sheetnames:
                ws_source = wb_source[sheet_name]

                # 处理sheet名称冲突
                new_sheet_name = sheet_name
                counter = 1
                while new_sheet_name in wb_output.sheetnames:
                    new_sheet_name = f"{sheet_name}_{counter}"
                    counter += 1

                # 创建新sheet
                ws_new = wb_output.create_sheet(title=new_sheet_name)

                # 手动复制单元格内容和样式
                for row in ws_source.iter_rows():
                    for cell in row:
                        new_cell = ws_new.cell(row=cell.row, column=cell.column, value=cell.value)

                        # 复制样式
                        if cell.has_style:
                            new_cell.font = cell.font.copy()
                            new_cell.border = cell.border.copy()
                            new_cell.fill = cell.fill.copy()
                            new_cell.number_format = cell.number_format
                            new_cell.protection = cell.protection.copy()
                            new_cell.alignment = cell.alignment.copy()

                # 手动复制图表（关键步骤！）
                for chart in ws_source._charts:
                    try:
                        anchor = chart.anchor
                        ws_new.add_chart(chart, anchor)
                    except Exception as e:
                        # 图表复制失败时继续，不影响其他内容
                        pass

                merged_count += 1

            wb_source.close()

        # 保存输出文件
        output_path = os.path.abspath(output_path)
        wb_output.save(output_path)
        wb_output.close()

        # 打印预览触发
        print(f"EXCEL_SAVED:{output_path}")

        return {
            "success": True,
            "merged_count": merged_count + 1,  # 第一个文件也算
            "file_path": output_path,
            "message": f"成功合并 {len(file_paths)} 个文件（图表和格式已保留）"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"合并失败: {str(e)}"
        }

# ===== Excel 辅助函数注入完成 =====

'''

        injected_code = helper_code + code

        # ✅ 新增：检测LLM是否直接使用openpyxl/pandas读取Excel，自动添加预览触发
        import re
        auto_preview_code = self._auto_add_excel_preview_trigger(code)
        if auto_preview_code:
            injected_code = helper_code + auto_preview_code
            logger.info(
                "excel_auto_preview_added",
                original_length=len(code),
                injected_length=len(injected_code),
                auto_preview_length=len(auto_preview_code) - len(code)
            )

        logger.info(
            "excel_injection_completed",
            original_length=len(code),
            injected_length=len(injected_code),
            injection_type="excel_helpers"
        )

        return injected_code

    def _auto_add_excel_preview_trigger(self, code: str) -> str:
        """
        自动检测Excel文件路径并添加预览触发

        检测模式：
        - file_path = 'xxx.xlsx'
        - file_path = "xxx.xlsx"
        - load_workbook('xxx.xlsx')
        - read_excel('xxx.xlsx')
        """
        import re
        import os

        # 正则模式：提取Excel文件路径
        patterns = [
            # file_path = 'xxx.xlsx' 或 file_path = "xxx.xlsx"
            r"file_path\s*=\s*['\"]([^'\"]+\.(xlsx|xls))['\"]",
            # load_workbook('xxx.xlsx') 或 load_workbook("xxx.xlsx")
            r"load_workbook\(['\"]([^'\"]+\.(xlsx|xls))['\"]",
            # read_excel('xxx.xlsx') 或 read_excel("xxx.xlsx")
            r"read_excel\(['\"]([^'\"]+\.(xlsx|xls))['\"]",
        ]

        extracted_paths = set()
        for pattern in patterns:
            matches = re.findall(pattern, code)
            for match in matches:
                extracted_paths.add(match[0])

        if not extracted_paths:
            logger.debug("auto_preview_skipped", reason="no_excel_file_path_found")
            return code

        # 在代码末尾添加预览触发
        preview_trigger_lines = [
            "\n# ===== 自动添加：Excel预览触发 =====",
            "import os",
        ]

        for file_path in extracted_paths:
            # 规范化路径
            preview_trigger_lines.append(f"print('EXCEL_SAVED:' + os.path.abspath('{file_path}'))")

        preview_trigger_lines.append("# ===== 预览触发完成 =====\n")

        modified_code = code + "\n" + "\n".join(preview_trigger_lines)

        logger.info(
            "auto_preview_trigger_added",
            excel_files=list(extracted_paths),
            lines_added=len(preview_trigger_lines)
        )

        return modified_code

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

        # 常见的文件保存模式（支持中文路径）
        patterns = [
            # EXCEL_SAVED:/path/to/文件名.xlsx
            r'EXCEL_SAVED[:：]\s*(.+?\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt))',
            # 报告已生成：/path/to/文件名.docx
            r'(?:报告已生成|文件已保存|已生成|保存成功|File saved|saved)[:：]\s*(.+?\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt))',
            # 文件名.xlsx（带中文的后缀）
            r'(.+?\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt))\s*[已]*[保存生成]*',
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

    def _format_python_error(self, error: Exception, code: str) -> Dict[str, str]:
        """
        格式化 Python 错误信息，提供详细的错误上下文和修复建议

        Args:
            error: Python 异常对象
            code: 执行的代码

        Returns:
            包含错误详情的字典
        """
        import traceback
        import re

        error_type = type(error).__name__
        error_msg = str(error)
        error_lines = traceback.format_exception(type(error), error, error.__traceback__)

        # 提取行号
        line_number = None
        for line in error_lines:
            match = re.search(r'File "<ipython-input-\d+>", line (\d+)', line)
            if match:
                line_number = int(match.group(1))
                break

        # 获取错误行的代码上下文
        code_context = ""
        if line_number:
            code_lines = code.split('\n')
            if 0 < line_number <= len(code_lines):
                error_line = code_lines[line_number - 1].strip()
                code_context = f"错误行代码（第{line_number}行）: {error_line}"

        # 常见错误的修复建议
        suggestions = self._get_error_suggestions(error_type, error_msg, code_context)

        # 构建详细的错误信息
        detailed_error = f"❌ Python 执行错误\n\n"
        detailed_error += f"**错误类型**: {error_type}\n"
        detailed_error += f"**错误信息**: {error_msg}\n"
        if line_number:
            detailed_error += f"**错误行号**: {line_number}\n"
        if code_context:
            detailed_error += f"{code_context}\n"
        if suggestions:
            detailed_error += f"\n**💡 修复建议**:\n{suggestions}\n"

        logger.warning(
            "python_execution_error",
            error_type=error_type,
            error_msg=error_msg,
            line_number=line_number,
            has_suggestions=bool(suggestions)
        )

        return {
            "error_type": error_type,
            "error_message": detailed_error,
            "summary": f"❌ 执行失败: {error_type} - {error_msg}",
            "line_number": line_number,
            "code_context": code_context,
            "suggestions": suggestions
        }

    def _get_error_suggestions(self, error_type: str, error_msg: str, code_context: str) -> str:
        """
        根据错误类型提供修复建议

        Args:
            error_type: 错误类型
            error_msg: 错误消息
            code_context: 错误行的代码上下文

        Returns:
            修复建议字符串
        """
        suggestions = []

        if error_type == "TypeError":
            if "can only concatenate str" in error_msg:
                suggestions.append("• **类型不匹配**: 尝试将字符串和数字相加")
                suggestions.append("• **解决方案**: 使用 `float()` 或 `int()` 转换变量类型")
                if "wind_dir" in code_context or "wind_direction" in code_context:
                    suggestions.append("• **示例修复**: `float(wind_dir) + 11.25` 而不是 `wind_dir + 11.25`")
                suggestions.append("• **JSON 数据注意**: 从 JSON 读取的数字可能是字符串类型")

            elif "unsupported operand type" in error_msg:
                suggestions.append("• **运算符不支持**: 操作数类型不匹配")
                suggestions.append("• **解决方案**: 检查变量类型，使用 `type()` 查看类型，使用 `int()`/`float()`/`str()` 转换")

            elif "not subscriptable" in error_msg:
                suggestions.append("• **不可下标访问**: 尝试对非列表/字典类型使用索引")
                suggestions.append("• **解决方案**: 检查变量是否为列表或字典，使用 `list()` 或 `dict()` 转换")

        elif error_type == "KeyError":
            suggestions.append("• **键不存在**: 字典中没有指定的键")
            suggestions.append("• **解决方案1**: 使用 `.get(key, default)` 方法提供默认值")
            suggestions.append("• **解决方案2**: 检查键名是否正确（区分大小写）")
            suggestions.append("• **示例修复**: `value = data.get('PM2_5', 0)` 而不是 `value = data['PM2_5']`")

        elif error_type == "NameError":
            suggestions.append("• **变量未定义**: 使用了未声明的变量")
            suggestions.append("• **解决方案**: 检查变量名拼写，确保变量已定义")

        elif error_type == "ValueError":
            if "could not convert string to float" in error_msg:
                suggestions.append("• **字符串转换失败**: 无法将字符串转换为数字")
                suggestions.append("• **解决方案**: 检查数据是否包含非数字字符，使用 `try-except` 处理异常")
                suggestions.append("• **示例修复**: `try: val = float(s) except: val = 0`")

            elif "I/O operation on closed file" in error_msg:
                suggestions.append("• **文件已关闭**: 尝试操作已关闭的文件对象")
                suggestions.append("• **解决方案**: 确保文件在 `with` 块内操作，或重新打开文件")

        elif error_type == "AttributeError":
            if "'NoneType' object has no attribute" in error_msg:
                suggestions.append("• **空对象属性**: 尝试访问 None 对象的属性")
                suggestions.append("• **解决方案**: 检查对象是否为 None，添加空值检查")
                suggestions.append("• **示例修复**: `if obj is not None: obj.method()`")

            else:
                suggestions.append("• **属性不存在**: 对象没有该属性或方法")
                suggestions.append("• **解决方案**: 检查对象类型，使用 `dir()` 查看可用属性")

        elif error_type == "IndexError":
            suggestions.append("• **索引越界**: 列表索引超出范围")
            suggestions.append("• **解决方案**: 检查列表长度，使用 `len()` 确保索引有效")
            suggestions.append("• **示例修复**: `if i < len(lst): value = lst[i]`")

        elif error_type == "FileNotFoundError":
            suggestions.append("• **文件不存在**: 找不到指定的文件")
            suggestions.append("• **解决方案**: 检查文件路径是否正确，使用绝对路径或相对于当前目录的路径")

        elif error_type == "ZeroDivisionError":
            suggestions.append("• **除零错误**: 尝试除以零")
            suggestions.append("• **解决方案**: 检查除数是否为零，添加条件判断")
            suggestions.append("• **示例修复**: `if divisor != 0: result = a / divisor`")

        elif error_type == "SyntaxError":
            suggestions.append("• **语法错误**: 代码语法不正确")
            suggestions.append("• **常见原因**: 括号不匹配、冒号缺失、缩进错误")
            suggestions.append("• **解决方案**: 检查括号、引号是否配对，检查缩进是否正确")

        # 如果没有特定建议，提供通用建议
        if not suggestions:
            suggestions.append("• **检查代码**: 仔细阅读错误信息，定位问题代码")
            suggestions.append("• **打印调试**: 使用 `print()` 输出变量值和类型")
            suggestions.append("• **异常处理**: 使用 `try-except` 捕获异常")

        return "\n".join(suggestions)

    def _parse_subprocess_error(self, stderr: str, code: str) -> Dict[str, str]:
        """
        解析 subprocess 模式的错误信息

        Args:
            stderr: 标准错误输出
            code: 执行的代码

        Returns:
            包含错误详情的字典
        """
        import re

        # 尝试提取错误类型和错误消息
        error_type = "UnknownError"
        error_msg = stderr.strip() if stderr else "未知错误"

        # 常见 Python 错误模式
        patterns = [
            r"(NameError|TypeError|ValueError|KeyError|AttributeError|IndexError|FileNotFoundError|ZeroDivisionError|SyntaxError): (.+)",
            r"Traceback \(most recent call last\):\s+.*\s+(NameError|TypeError|ValueError|KeyError|AttributeError|IndexError|FileNotFoundError|ZeroDivisionError|SyntaxError): (.+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr)
            if match:
                error_type = match.group(1)
                error_msg = match.group(2).strip()
                break

        # 提取行号
        line_number = None
        line_match = re.search(r'File "<string>", line (\d+)', stderr)
        if line_match:
            line_number = int(line_match.group(1))

        # 获取错误行的代码上下文
        code_context = ""
        if line_number:
            code_lines = code.split('\n')
            if 0 < line_number <= len(code_lines):
                error_line = code_lines[line_number - 1].strip()
                code_context = f"错误行代码（第{line_number}行）: {error_line}"

        # 获取修复建议
        suggestions = self._get_error_suggestions(error_type, error_msg, code_context)

        # 构建详细的错误信息
        detailed_error = f"❌ Python 执行错误\n\n"
        detailed_error += f"**错误类型**: {error_type}\n"
        detailed_error += f"**错误信息**: {error_msg}\n"
        if line_number:
            detailed_error += f"**错误行号**: {line_number}\n"
        if code_context:
            detailed_error += f"{code_context}\n"
        if suggestions:
            detailed_error += f"\n**💡 修复建议**:\n{suggestions}\n"

        return {
            "error_type": error_type,
            "error_message": detailed_error,
            "summary": f"❌ 执行失败: {error_type} - {error_msg}",
            "line_number": line_number,
            "code_context": code_context,
            "suggestions": suggestions
        }

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
                "【⚠️ 常见错误预防】\n"
                "• **类型转换错误**: 从 JSON 读取的数据可能是字符串，需要使用 float() 或 int() 转换\n"
                "  - ❌ 错误：`dir_idx = int((wind_dir + 11.25) / 22.5) % 16`  （wind_dir 是字符串）\n"
                "  - ✅ 正确：`dir_idx = int((float(wind_dir) + 11.25) / 22.5) % 16`\n"
                "• **字典键不存在**: 使用 .get() 方法避免 KeyError\n"
                "  - ❌ 错误：`pm25 = record['PM2_5']`\n"
                "  - ✅ 正确：`pm25 = record.get('PM2_5', 0)`  （提供默认值）\n"
                "• **空值检查**: 使用变量前检查是否为 None\n"
                "  - ✅ 正确：`if value is not None: result = float(value) + 10`\n\n"
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
