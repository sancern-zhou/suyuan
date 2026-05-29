# -*- coding: utf-8 -*-
"""
Execute Python Code Tool

执行 Python 代码工具（用于数据处理、可视化、中间资源生成）

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
import re
import ast
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.path_config import get_charts_dir, get_data_registry, get_images_dir, get_python_output_dir, get_reports_dir
from app.tools.system.data_registry_read_state import get_data_registry_read_state

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
        # 永久文件存储目录（统一使用 backend/backend_data_registry）
        self.PERMANENT_DIR = str(get_data_registry() / "python_generated_files")

        # ✅ 图表文件存储目录
        self.CHARTS_DIR = str(get_charts_dir())
        self.REPORTS_DIR = str(get_reports_dir())

        # 确保永久目录和图表目录存在
        os.makedirs(self.PERMANENT_DIR, exist_ok=True)
        os.makedirs(self.CHARTS_DIR, exist_ok=True)
        os.makedirs(self.REPORTS_DIR, exist_ok=True)

        super().__init__(
            name="execute_python",
            description=f"""执行 Python 代码（用于数据处理、可视化、中间资源生成）

    重要说明：
    - 每次调用都是独立执行环境；上一次 execute_python 中定义的变量、函数、DataFrame 不会保留
    - 使用工具返回的 data_id/report_data_id 计算前，必须先调用 read_data_registry 读取所需视图/字段；execute_python 的 get_raw_data 只返回已读取的数据快照
    - 需要跨多次工具调用复用的中间结果，必须显式调用 `save_data(...)` 保存为 data_id，后续先用 read_data_registry 读取再计算
- 不要在后续 execute_python 调用中直接引用前一次脚本里的变量名（如 city_map、df、report_data）
- 统一数据目录：{get_data_registry()}
- 当前工作目录：{self.PERMANENT_DIR}
- 图表保存目录：{self.CHARTS_DIR}
- 报告资源保存目录：{self.REPORTS_DIR}
- 生成图表、表格、临时文件、Office 文件必须保存到上述统一数据目录下；不要使用 `/home/xckj/suyuan/backend_data_registry/...`
- 推荐使用相对路径（如：'report.docx'）或统一目录绝对路径（如：'{self.CHARTS_DIR}/report.docx'）
- 工具会自动将生成的文件保存到永久目录，并返回完整路径
- 支持 python-docx, matplotlib, pandas, openpyxl 等所有 Python 库
- 超时时间：30秒（可调整）

📄 正式报告工具边界：
- 正式报告默认使用 `create_report_package` 保存 `reports/{{report_id}}/report.qmd` 并触发右侧面板预览。
- execute_python 主要用于计算、制图、整理表格、生成报告包所需的本地相对路径资源，不作为正式报告最终交付工具。
- 流程图、架构图、步骤图、决策树不要优先用 execute_python 生成 DOT/SVG；应直接使用 `create_flowchart_artifact`。
- 不要在 Python 脚本里手写正式报告的 HTML/Word/PPT 转换流程；下载 HTML/Word/PPT/QMD 和分享 HTML 链接由右侧面板按钮触发固定后端报告 API。
- 只有用户明确要求“一次性 Word/Office 文件”且不需要 qmd/HTML/PPT 同源报告包时，才直接用 python-docx/openpyxl/python-pptx 生成 Office 文件。
- 用户明确要求演讲材料、展示页、数据大屏、交互网页或可视化叙事时，先用本工具准备图表/数据/资源，再用 create_html_artifact 收口为 HTML 展示产物。

📊 图表保存与前端渲染：
- 系统自动注入 save_chart() 辅助函数
- 使用 save_chart(fig, 'chart.png') 保存图表，自动生成 /api/image/{{image_id}} URL
- 也可以直接使用 plt.savefig()，系统会智能识别路径并缓存
- 默认注入“政府报告图表模板”：自动把常规图表的画布、字号、网格、边距调整到报告可读性优先的默认值
- 默认遵循“一张图片只表达一个核心图表/分析问题”：除非用户明确要求“多子图/组合图/仪表盘/一页多图对比”，不要在同一个 Figure 中使用 subplot/subplots/多 Axes 拼接多个图表。
- 同一数据源可用于多个分析视角，但应按用户问题选择最相关的一张图；确需多个独立图表时，分别生成多个图片文件并使用清晰文件名，不要合并到单张图片里。
- 绘制单个时序/柱状/散点图时，可以在同一个坐标轴中放多条系列用于对比；这不属于“多图拼接”。但不要把折线图、柱状图、饼图等不同图表并排塞进同一张图片。
- 示例代码见下方

📄 HTML输出兼容说明：
- 系统仍兼容 save_html_report(report_id, html_content, assets_dir=None)，用于轻量 HTML 或旧流程。
- 正式报告不要优先使用 save_html_report 交付；应生成 qmd 内容和相对路径资源后调用 create_report_package。
- qmd 图片最终必须使用报告包内相对路径，如 `assets/charts/chart_01.png`，不要使用 `/api/image/...`。
  生成报告包时不要自行根据 `/api/image/{{image_id}}` 或缓存 id 推断该路径；应把真实图片文件路径作为
  `create_report_package.assets[].path` 传入，并用可选 `name` 指定稳定文件名，由 create_report_package 复制和规范化引用。

    📊 数据访问功能（自动注入）：
    当工具检测到 context 时，会自动注入 `get_raw_data(data_id)` 和 `save_data(data, ...)` 函数：
    - `get_raw_data(data_id)`: 返回 read_data_registry 已读取的数据快照；未先读取会报错。
    - `save_data(data, schema='python_result', metadata=None)`: 将中间结果保存到数据注册表并返回 data_id

    使用示例：
    ```python
    # 先用 read_data_registry 读取数据，再把已返回的小规模数据用于计算
    data = [
        {{'city': '广州', 'o3_primary_days': 120, 'valid_days': 365}},
        {{'city': '深圳', 'o3_primary_days': 110, 'valid_days': 365}},
    ]
    ratio = sum(row['o3_primary_days'] for row in data) / sum(row['valid_days'] for row in data)
    print(f"臭氧首要污染物占比: {{ratio:.2%}}")

    # 保存后续还要复用的中间结果
    result_id = save_data(
        [{{'metric': 'o3_primary_ratio', 'value': ratio}}],
        schema='python_result',
        metadata={{'purpose': 'report_check_intermediate'}}
    )
    print(f"中间结果 data_id: {{result_id}}")
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
- 不要在代码中指定中文字体、字体文件或字体族；系统会自动注入并在保存图片前强制应用后端统一中文字体。
- 不要写 `FontProperties(...)`、`plt.rcParams['font.family']`、`plt.rcParams['font.sans-serif']`、`matplotlib.rcParams[...]` 或 `fontfamily=...` 来控制中文字体。
- 只需要正常设置中文标题、坐标轴、图例文本即可。

📊 图表保存示例（推荐使用save_chart辅助函数）：
```python
import matplotlib.pyplot as plt
import numpy as np

# 创建图表
fig, ax = plt.subplots()
x = np.linspace(0, 10, 100)
ax.plot(x, np.sin(x))
ax.set_xlabel('横轴')
ax.set_ylabel('纵轴')
ax.set_title('示例图表')

# ✅ 推荐：使用save_chart辅助函数（自动生成 /api/image/{{image_id}} URL）
save_chart(fig, 'example_chart.png', dpi=150)

# ✅ 也支持：直接使用plt.savefig（系统会智能识别路径）
plt.savefig('chart2.png', dpi=150)
print('图表已保存: chart2.png')  # 系统会自动提取路径
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

    def _validate_data_registry_pre_read(self, code: str) -> Optional[Dict[str, Any]]:
        """Require read_data_registry before Python reads a DataRegistry id.

        This is intentionally tool-level and mode-independent, mirroring the
        read_file/edit_file read-before-edit contract. Pure calculations over
        literal data are unaffected.
        """
        result = self._find_data_registry_accesses(code)
        if result["direct_registry_access"]:
            return self._data_registry_pre_read_error(
                reason=result["direct_registry_access"][0],
                data_id=None,
                details="execute_python 不允许直接导入或调用 DataRegistry 底层读取接口；请先使用 read_data_registry。"
            )

        state = get_data_registry_read_state()
        for data_id in result["get_raw_data_ids"]:
            record = state.get(data_id)
            if not record:
                return self._data_registry_pre_read_error(
                    reason="data_id_not_read",
                    data_id=data_id,
                    details=f"data_id {data_id} 尚未通过 read_data_registry 读取。"
                )
            if not record.is_data_snapshot:
                return self._data_registry_pre_read_error(
                    reason="metadata_only_read",
                    data_id=data_id,
                    details=(
                        f"data_id {data_id} 只读取了字段/视图结构，尚未读取可用于计算的数据视图。"
                    )
                )

        if result["unknown_get_raw_data"]:
            return self._data_registry_pre_read_error(
                reason="dynamic_data_id",
                data_id=None,
                details="get_raw_data 的 data_id 必须是字符串字面量，或赋值为字符串字面量的变量，以便校验是否已读取。"
            )

        return None

    def _find_data_registry_accesses(self, code: str) -> Dict[str, Any]:
        get_raw_data_ids: List[str] = []
        unknown_get_raw_data = False
        direct_registry_access: List[str] = []
        assigned_strings: Dict[str, str] = {}

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Let the Python executor surface syntax errors. Only catch obvious
            # pre-read bypasses in unparsable snippets.
            direct_registry_access.extend(
                token for token in ("app.services.data_registry", "backend_data_registry")
                if token in code
            )
            if re.search(r"\bget_raw_data\s*\(", code):
                unknown_get_raw_data = True
            return {
                "get_raw_data_ids": get_raw_data_ids,
                "unknown_get_raw_data": unknown_get_raw_data,
                "direct_registry_access": direct_registry_access,
            }

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned_strings[target.id] = node.value.value

            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in {"app.services.data_registry", "backend_data_registry"}:
                    direct_registry_access.append(f"import from {module}")

            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "backend_data_registry":
                        direct_registry_access.append("import backend_data_registry")

            if isinstance(node, ast.Call):
                func_name = self._call_name(node.func)
                if func_name == "get_raw_data":
                    if not node.args:
                        unknown_get_raw_data = True
                    else:
                        data_id = self._literal_or_assigned_string(node.args[0], assigned_strings)
                        if data_id:
                            get_raw_data_ids.append(data_id)
                        else:
                            unknown_get_raw_data = True

                if func_name.endswith(".load_dataset") or func_name.endswith(".load_payload"):
                    direct_registry_access.append(func_name)

        return {
            "get_raw_data_ids": list(dict.fromkeys(get_raw_data_ids)),
            "unknown_get_raw_data": unknown_get_raw_data,
            "direct_registry_access": direct_registry_access,
        }

    def _call_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._call_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    def _literal_or_assigned_string(self, node: ast.AST, assigned_strings: Dict[str, str]) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return assigned_strings.get(node.id)
        return None

    def _data_registry_pre_read_error(
        self,
        *,
        reason: str,
        data_id: Optional[str],
        details: str,
    ) -> Dict[str, Any]:
        logger.warning(
            "execute_python_data_registry_pre_read_required",
            reason=reason,
            data_id=data_id,
        )
        return {
            "status": "failed",
            "success": False,
            "error": (
                "使用 DataRegistry 数据计算前必须先调用 read_data_registry 读取数据。"
                f"{details}"
            ),
            "data": None,
            "metadata": {
                "tool_name": "execute_python",
                "blocked_by": "data_registry_read_before_compute",
                "reason": reason,
                "data_id": data_id,
            },
            "summary": "执行失败：请先使用 read_data_registry 读取 data_id/report_data_id 后再计算。",
        }

    def _build_read_snapshot_payload(self, code: str) -> str:
        """Serialize read_data_registry snapshots referenced by get_raw_data."""
        try:
            accesses = self._find_data_registry_accesses(code)
            state = get_data_registry_read_state()
            snapshots = {}
            for data_id in accesses.get("get_raw_data_ids", []):
                record = state.get(data_id)
                if record and record.is_data_snapshot:
                    snapshots[data_id] = record.data
            return json.dumps(snapshots, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.warning("data_registry_snapshot_payload_build_failed", error=str(exc))
            return "{}"

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

        pre_read_error = self._validate_data_registry_pre_read(code)
        if pre_read_error:
            return pre_read_error

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

                # ✅ 注入标准报告保存辅助函数
                code = self._inject_report_helpers(code)

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

                # ✅ 注入标准报告保存辅助函数
                code = self._inject_report_helpers(code)

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
            result["data"]["artifact_schema"] = self._artifact_schema()

            # ✅ DOCX 后处理：优先用同目录 report.html 作为源重建正式 Word；
            # 若没有 HTML 源，再兜底替换图片占位符。
            docx_postprocess = []
            for generated_file in final_files:
                if Path(generated_file).suffix.lower() != ".docx":
                    continue
                try:
                    from app.services.report.government_docx_style import (
                        convert_html_report_to_government_docx,
                        infer_report_html_path_for_docx,
                        replace_image_placeholders_in_docx,
                    )

                    html_path = infer_report_html_path_for_docx(generated_file)
                    if html_path:
                        cleanup = convert_html_report_to_government_docx(html_path, generated_file)
                        logger.info(
                            "execute_python_docx_rebuilt_from_html_report",
                            file=generated_file,
                            html_path=str(html_path),
                            embedded_images=cleanup.get("embedded_images"),
                            missing_images=cleanup.get("missing_images", [])
                        )
                    else:
                        cleanup = replace_image_placeholders_in_docx(generated_file)
                        if cleanup.get("replaced", 0):
                            logger.info(
                                "execute_python_docx_images_embedded",
                                file=generated_file,
                                replaced=cleanup.get("replaced"),
                                missing=cleanup.get("missing", [])
                            )
                    docx_postprocess.append(cleanup)
                except Exception as cleanup_error:
                    logger.warning(
                        "execute_python_docx_postprocess_failed",
                        file=generated_file,
                        error=str(cleanup_error)
                    )
            if docx_postprocess:
                result["data"]["docx_postprocess"] = docx_postprocess

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

            # ✅ 处理展示型 HTML：统一归档到 html_artifacts/{artifact_id}/index.html 并返回 html_preview
            html_files = [f for f in final_files if Path(f).suffix.lower() in {'.html', '.htm'}]
            if html_files and "html_preview" not in result["data"] and "file_path" not in result["data"]:
                html_report = self._standardize_html_report(html_files[0], backend_dir)
                if html_report:
                    report_path = html_report["file_path"]
                    result["data"]["html_preview"] = html_report["html_preview"]
                    result["data"]["file_path"] = report_path
                    result["data"]["file_type"] = "html_artifact"
                    if report_path not in result["data"]["files"]:
                        result["data"]["files"].append(report_path)
                    if result.get("success", False):
                        result["summary"] = f"✅ 工具已执行完成，生成HTML展示页：{Path(report_path).name}"
                    logger.info(
                        "execute_python_html_artifact_standardized",
                        source_file=html_files[0],
                        artifact_id=html_report.get("artifact_id"),
                        report_path=report_path,
                        html_url=html_report["html_preview"]["html_url"],
                    )

            # ✅ 检测图表输出（CHART_SAVED:xxx.png 或 CHART_SAVED:data:image/png;base64,...）
            chart_data = self._extract_chart_paths(result["data"].get("output", ""))

            # ✅ 检测 Python 中通过 save_data() 保存的 data_id
            python_data_refs = self._extract_python_data_refs(result["data"].get("output", ""))
            if python_data_refs:
                result["data"]["data_ids"] = python_data_refs
                result["data_ids"] = python_data_refs
                result.setdefault("metadata", {})
                result["metadata"]["data_ids"] = python_data_refs
                if result.get("success", False):
                    result["summary"] = (
                        f"{result.get('summary', '✅ 工具已执行完成')} | "
                        f"已保存中间结果 data_id: {', '.join(python_data_refs)}"
                    )

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
                                    "url": image_info["url"],  # /api/image/{image_id}（前端用）
                                    "image_id": image_info["image_id"],
                                    "local_path": image_info["local_path"],  # 图片缓存真实本地路径
                                    "source_file_path": abs_chart_path,  # execute_python 生成的真实图片路径
                                },
                                "meta": {
                                    "generator": "execute_python",
                                    "schema_version": "3.1",
                                    "file_path": abs_chart_path,
                                    "report_asset_hint": {
                                        "path": abs_chart_path,
                                        "type": "image",
                                        "name": Path(chart_path).name,
                                    },
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
                                    "url": image_info["url"],  # /api/image/{image_id}（前端用）
                                    "image_id": image_info["image_id"],
                                    "local_path": image_info["local_path"],  # 图片缓存真实本地路径
                                    "source_file_path": image_info["local_path"],
                                },
                                "meta": {
                                    "generator": "execute_python",
                                    "schema_version": "3.1",
                                    "source": "base64_output",
                                    "report_asset_hint": {
                                        "path": image_info["local_path"],
                                        "type": "image",
                                        "name": f"{chart_id}.png",
                                    },
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
                    # 使用计数器确保同一工具生成的多个图表有唯一ID
                    echarts_count = len([v for v in result.get("visuals", []) if v.get("id", "").startswith("echarts_")])
                    result.setdefault("visuals", []).append({
                        "id": f"echarts_{time.time_ns()}_{echarts_count}",
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
                    if not chart_data.get("paths") and not chart_data.get("base64_data"):  # 如果没有matplotlib图表，使用ECharts摘要
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

    def _artifact_schema(self) -> Dict[str, Any]:
        """Return a compact schema note for generated artifacts."""
        return {
            "version": "execute_python.artifacts.v1",
            "files": "All generated local files as absolute paths.",
            "file_path": "Primary generated file for preview/download.",
            "pdf_preview": "Office/PDF preview metadata for docx/xlsx/pptx/pdf artifacts.",
            "html_preview": "HTML preview metadata. Notebook uses /api/notebook/html/{html_id}; HTML artifacts use /api/html-artifacts/{artifact_id}/html; reports use /api/reports/{report_id}/html.",
            "visuals": "Image/ECharts blocks for frontend rendering. Matplotlib images are cached under /api/image/{image_id}.",
            "html_artifact_layout": "Presentation HTML artifacts live at backend_data_registry/html_artifacts/{artifact_id}/index.html.",
        }

    def _safe_report_id(self, raw_id: str) -> str:
        """Normalize an HTML artifact id."""
        report_id = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_id.strip())
        report_id = report_id.strip("_")
        return report_id or f"html_report_{int(time.time())}"

    def _standardize_html_report(self, html_file: str, backend_dir: str) -> Optional[Dict[str, Any]]:
        """
        Move/copy a generated standalone HTML file into the HTML artifact store.

        This is a compatibility fallback for older execute_python snippets that wrote
        a bare .html file instead of using create_html_artifact.
        """
        source = Path(html_file).resolve()
        if not source.exists() or not source.is_file():
            return None

        artifact_id = self._safe_report_id(source.stem)
        assets = []
        for sibling_name in ("assets", "images", "report_files"):
            sibling = source.parent / sibling_name
            if sibling.exists() and sibling.is_dir():
                assets.append({"path": str(sibling), "name": sibling.name})

        try:
            from app.services.html_artifact_service import html_artifact_service

            data = html_artifact_service.create_artifact(
                artifact_id,
                source.read_text(encoding="utf-8", errors="replace"),
                title=source.stem,
                assets=assets,
                metadata={"source": "execute_python_html_file"},
            )
        except Exception as exc:
            logger.warning("execute_python_html_artifact_standardize_failed", source_file=str(source), error=str(exc))
            return None

        return {
            "report_id": data["artifact_id"],
            "artifact_id": data["artifact_id"],
            "file_path": data["file_path"],
            "html_preview": data["html_preview"],
        }

    def _extract_chart_paths(self, output: str) -> dict:
        """
        从 Python 代码输出中提取图表路径和base64数据

        检测格式：
        1. CHART_SAVED:/path/to/chart.png (标准格式)
        2. 图表已保存: /path/to/chart.png (中文格式)
        3. 图表已保存到: /path/to/chart.png (中文格式2)
        4. 保存成功: /path/to/chart.png (中文格式3)
        5. CHART_SAVED:data:image/png;base64,... (base64数据)

        Args:
            output: Python 代码输出

        Returns:
            {"paths": [文件路径列表], "base64_data": [base64数据列表]}
        """
        import re
        result = {"paths": [], "base64_data": []}
        output_lines = output.split('\n')

        # 图表文件扩展名
        image_extensions = r'\.(?:png|jpg|jpeg|svg|pdf|gif|bmp|tiff)'

        for line in output_lines:
            line = line.strip()

            # 检测标准格式
            if line.startswith("CHART_SAVED:"):
                chart_data = line.split("CHART_SAVED:")[1].strip()

                if chart_data.startswith("data:image/"):
                    result["base64_data"].append(chart_data)
                else:
                    result["paths"].append(chart_data)

            # 检测中文输出格式（智能匹配）
            else:
                # 常见的中文图表保存模式
                chinese_patterns = [
                    # 图表已保存: /path/to/chart.png
                    rf'(?:图表已保存|图表已保存到|保存成功|图片已保存|图片已保存到|已生成图表)[:：]\s*(.+?{image_extensions})',
                    # 保存图表到 /path/to/chart.png
                    rf'(?:保存图表到|生成图表到|图表保存到)[:：]\s*(.+?{image_extensions})',
                    # 直接以文件路径结尾（带图表扩展名）
                    rf'^(.+?{image_extensions})\s*(?:$|已保存|生成完成)',
                ]

                for pattern in chinese_patterns:
                    matches = re.findall(pattern, line)
                    for match in matches:
                        if match and match not in result["paths"]:
                            result["paths"].append(match)

        return result

    def _extract_python_data_refs(self, output: str) -> List[str]:
        """Extract data_ids printed by the injected save_data() helper."""
        if not output:
            return []
        refs: List[str] = []
        for match in re.findall(r"PYTHON_DATA_SAVED:([A-Za-z0-9_:\-\.]+)", output):
            if match and match not in refs:
                refs.append(match)
        return refs

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
        - save_data(data, schema="python_result", metadata=None): 保存中间结果并返回 data_id

        ⚠️ 重要：
        - 每次 execute_python 都是独立执行环境，不保留上次调用的变量
        - LLM 应该在代码中直接使用 data_id
        - 跨工具调用复用的数据必须先 save_data，再在后续调用中 get_raw_data(data_id)
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

        snapshot_payload = self._build_read_snapshot_payload(code)

        # 构建注入的代码
        context_injection_code = '''# ===== 数据访问上下文（自动注入） =====
# 重要：每次 execute_python 都是独立执行环境，不保留上次调用的变量。
# 如果中间结果后续还要复用，请调用 save_data(...) 保存为 data_id；
# 后续 execute_python 调用中再用 get_raw_data(data_id) 显式读取。

__READ_DATA_REGISTRY_SNAPSHOTS__ = __SNAPSHOT_PAYLOAD__

# 获取原始数据（字典列表格式）
def get_raw_data(data_id: str):
    """获取 read_data_registry 已读取的数据快照。
    
    Args:
        data_id: 已通过 read_data_registry 读取过的数据ID
    
    Returns:
        read_data_registry 最近一次读取该 data_id 返回的 data
    """
    if data_id in __READ_DATA_REGISTRY_SNAPSHOTS__:
        return __READ_DATA_REGISTRY_SNAPSHOTS__[data_id]

    from app.tools.system.data_registry_read_state import get_data_registry_read_state

    record = get_data_registry_read_state().get(data_id)
    if record is None:
        raise RuntimeError(
            f"DataRegistry 数据 {data_id} 尚未读取。请先调用 read_data_registry(data_id=...)。"
        )
    if not record.is_data_snapshot:
        raise RuntimeError(
            f"DataRegistry 数据 {data_id} 当前只有结构信息，没有可计算数据。"
            "请先调用 read_data_registry 读取具体 view/fields。"
        )
    return record.data

def save_data(data, schema: str = 'python_result', metadata=None, version: str = 'v1'):
    """保存 Python 中间结果到数据注册表并返回 data_id。

    适用于跨多次 execute_python 调用复用的变量、DataFrame 转换结果、核验表等。
    data 可以是 list[dict]、dict、pandas DataFrame 或其他可 JSON 序列化对象。
    """
    import json
    from datetime import datetime
    from app.services.data_registry import data_registry

    if metadata is None:
        metadata = {}
    metadata = dict(metadata)
    metadata.setdefault('generator', 'execute_python')
    metadata.setdefault('created_by', 'save_data_helper')
    metadata.setdefault('created_at', datetime.utcnow().isoformat())

    try:
        import pandas as pd
        if isinstance(data, pd.DataFrame):
            payload = data.to_dict(orient='records')
        else:
            payload = data
    except Exception:
        payload = data

    def _json_default(value):
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        if hasattr(value, 'item'):
            return value.item()
        return str(value)

    payload = json.loads(json.dumps(payload, ensure_ascii=False, default=_json_default))

    if isinstance(payload, list):
        records = []
        for item in payload:
            if isinstance(item, dict):
                records.append(item)
            else:
                records.append({'value': item})
        if not records:
            records = [{'value': None}]
        entry = data_registry.register_dataset(
            schema=schema,
            version=version,
            records=records,
            metadata=metadata,
        )
    else:
        entry = data_registry.register_payload(
            schema=schema,
            version=version,
            payload=payload,
            metadata=metadata,
        )

    print(f"PYTHON_DATA_SAVED:{entry.data_id}")
    return entry.data_id

# ===== 数据访问上下文注入完成 =====

'''
        context_injection_code = context_injection_code.replace("__SNAPSHOT_PAYLOAD__", snapshot_payload)

        # 在代码开头插入上下文代码
        injected_code = context_injection_code + code

        logger.info(
            "data_context_injection_completed",
            original_length=len(code),
            injected_length=len(injected_code)
        )

        return injected_code

    def _inject_report_helpers(self, code: str) -> str:
        """Inject helpers for standardized report artifact output."""
        html_artifacts_dir = str(get_data_registry() / "html_artifacts").replace("\\", "\\\\").replace("'", "\\'")
        helper_code = f'''# ===== 报告输出辅助函数（自动注入） =====
# 展示型HTML统一保存为 backend_data_registry/html_artifacts/{{artifact_id}}/index.html
def save_html_artifact(artifact_id: str, html_content: str, assets_dir=None, extra_assets=None):
    """保存展示型 HTML 并打印标准预览标记。

    适用于演讲材料、数据大屏、交互说明页、可视化叙事等。
    正式报告请使用 create_report_package，不要用本函数交付。
    """
    import json
    import re
    import shutil
    from pathlib import Path

    artifacts_root = Path('{html_artifacts_dir}')
    safe_id = re.sub(r'[^A-Za-z0-9_-]+', '_', str(artifact_id).strip()).strip('_')
    if not safe_id:
        raise ValueError('artifact_id 不能为空')

    artifact_dir = artifacts_root / safe_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / 'index.html'
    artifact_path.write_text(html_content, encoding='utf-8')

    def _copy_dir(src, dst):
        src = Path(src)
        dst = Path(dst)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    if assets_dir:
        src = Path(assets_dir)
        if src.exists() and src.is_dir():
            assets_target = artifact_dir / 'assets'
            assets_target.mkdir(parents=True, exist_ok=True)
            if src.name == 'assets':
                _copy_dir(src, assets_target)
            else:
                _copy_dir(src, assets_target / src.name)

    for asset in (extra_assets or []):
        src = Path(asset)
        if not src.exists():
            continue
        assets_target = artifact_dir / 'assets'
        assets_target.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            _copy_dir(src, assets_target / src.name)
        else:
            shutil.copy2(src, assets_target / src.name)

    html_preview = {{
        'html_id': safe_id,
        'html_url': f'/api/html-artifacts/{{safe_id}}/html',
        'file_type': 'html_artifact',
        'schema_version': 'html_artifact.v1',
        'preview_version': str(int(artifact_path.stat().st_mtime)),
    }}
    result = {{
        'success': True,
        'artifact_id': safe_id,
        'file_path': str(artifact_path),
        'file_type': 'html_artifact',
        'html_preview': html_preview,
    }}
    print('HTML_ARTIFACT_SAVED:' + str(artifact_path))
    print('HTML_PREVIEW:' + json.dumps(html_preview, ensure_ascii=False))
    return result

# 兼容旧名称：轻量HTML/展示页走 html_artifact；正式报告仍应使用 create_report_package。
def save_html_report(report_id: str, html_content: str, assets_dir=None, extra_assets=None):
    return save_html_artifact(report_id, html_content, assets_dir=assets_dir, extra_assets=extra_assets)

# ===== 报告输出辅助函数注入完成 =====

'''
        return helper_code + code

    def _convert_unicode_subscript_to_latex(self, code: str) -> str:
        """
        自动转换Python代码字符串中的Unicode下标/上标字符为LaTeX格式

        策略：
        1. 使用正则表达式匹配所有字符串字面量
        2. 在字符串中检测Unicode下标/上标字符
        3. 转换为简写格式（避免LaTeX与中文混合问题）
        4. 智能处理多位数字（如2.5）

        ⚠️ 重要变更：
        由于matplotlib的mathtext引擎不支持中文字符，会导致混合LaTeX和中文的
        字符串显示异常。因此，我们采用简写格式替代LaTeX格式：
        - PM₂.₅ → PM2.5（而非 PM$_{2.5}$）
        - μg/m³ → ug/m3（而非 $\\mu$g/m$^3$）

        转换示例：
        - 'PM₂.₅浓度' → 'PM2.5浓度'
        - 'μg/m³' → 'ug/m3'
        - 'NO₂' → 'NO2'
        """
        import re

        def convert_string_content(content: str) -> tuple:
            """
            转换字符串内容

            Returns:
                (converted_content, needs_r_prefix)
            """
            # 定义常见模式的替换规则（使用简写格式，避免LaTeX与中文混合问题）
            replacements = [
                # μ符号
                (r'μ', r'u'),

                # PM2.5（特殊处理：小数形式）
                (r'PM₂\.?₅', r'PM2.5'),
                (r'pm₂\.?₅', r'pm2.5'),

                # 化学式下标（单个数字）- 简写格式
                (r'O₃', r'O3'),
                (r'NO₂', r'NO2'),
                (r'SO₂', r'SO2'),
                (r'CO₂', r'CO2'),
                (r'CH₄', r'CH4'),
                (r'N₂O', r'N2O'),
                (r'VOCs', r'VOCs'),  # 保持原样

                # 单位上标 - 简写格式
                (r'm³', r'm3'),
                (r'm²', r'm2'),
                (r'km²', r'km2'),
                (r'km³', r'km3'),
                (r'μg', r'ug'),

                # 其他上标数字（需要小数点前面的m等）
                (r'/m³', r'/m3'),
                (r'/m²', r'/m2'),
            ]

            new_content = content
            needs_r = False

            # 应用替换规则
            for old, new in replacements:
                if old in new_content:
                    new_content = new_content.replace(old, new)
                    needs_r = True

            # 处理剩余的Unicode下标/上标（兜底）
            subscript_digits = {
                '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
                '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9',
            }
            superscript_digits = {
                '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
                '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
            }

            # 检查是否还有未处理的下标
            has_remaining = any(c in new_content for c in subscript_digits.keys())
            has_remaining = has_remaining or any(c in new_content for c in superscript_digits.keys())

            if has_remaining:
                # 对于剩余的Unicode字符，使用简写格式替换
                for unicode_char, normal_char in subscript_digits.items():
                    if unicode_char in new_content:
                        new_content = new_content.replace(unicode_char, normal_char)
                        needs_r = True

                for unicode_char, normal_char in superscript_digits.items():
                    if unicode_char in new_content:
                        new_content = new_content.replace(unicode_char, normal_char)
                        needs_r = True

            return new_content, needs_r

        def process_match(match):
            """处理正则匹配的字符串"""
            full_match = match.group(0)

            # 提取引号类型和内容
            if full_match.startswith("'''") or full_match.startswith('"""'):
                # 三引号字符串，暂不处理
                return full_match
            elif full_match.startswith("'"):
                quote = "'"
                content = full_match[1:-1]
            elif full_match.startswith('"'):
                quote = '"'
                content = full_match[1:-1]
            else:
                return full_match

            # 转换内容（简写格式，不需要r前缀）
            converted_content, needs_r = convert_string_content(content)

            # 直接返回转换后的内容（不需要r前缀）
            return f'{quote}{converted_content}{quote}'

        # 匹配Python字符串字面量（排除已经有r前缀的）
        # 使用负向后查找排除r前缀
        string_pattern = r"""
            (?<![rR])                      # 前面不能有r或R
            (?:
                '''(?:[^\\]|\\.)*?'''     # 三单引号
                |\"\"\"(?:[^\\]|\\.)*?\"\"\"  # 三双引号
                |'(?:[^'\\]|\\.)*'        # 单引号
                |"(?:[^"\\]|\\.)*"        # 双引号
            )
        """
        string_pattern = re.compile(string_pattern, re.VERBOSE | re.DOTALL)

        # 执行转换
        converted_code = string_pattern.sub(process_match, code)

        # 统计转换次数
        original_matches = list(string_pattern.finditer(code))
        conversion_count = 0
        for m in original_matches:
            content = m.group(0)
            if any(c in content for c in ['₂', '₃', '⁵', '⁴', '⁶', '⁷', '⁸', '⁹', '⁰',
                                          '²', '³', '¹', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹', '⁰', 'μ']):
                conversion_count += 1

        if conversion_count > 0:
            logger.info(
                "unicode_subscript_converted",
                strings_converted=conversion_count
            )

        return converted_code

    def _inject_chinese_font_support(self, code: str) -> str:
        """
        自动注入中文字体支持代码

        策略：
        1. 在代码开头注册字体
        2. 自动转换Unicode下标/上标字符为LaTeX格式
        3. 替换用户错误的字体设置
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
        images_dir_literal = repr(str(get_images_dir()))
        font_registration_code = """# ===== 自动注入中文字体支持 =====
import os
from pathlib import Path

# ===== Matplotlib 图片保存兜底（自动注入） =====
_SUYUAN_CHART_PATHS_EMITTED = set()

def _suyuan_emit_chart_saved(path):
    '''输出标准图片保存标记，供 execute_python 后处理缓存到 /api/image/{image_id}。'''
    try:
        if path is None:
            return
        if isinstance(path, (str, os.PathLike)):
            chart_path = os.path.abspath(os.fspath(path))
        else:
            # BytesIO 等文件对象无法直接作为前端图片缓存路径处理。
            return
        if chart_path not in _SUYUAN_CHART_PATHS_EMITTED:
            _SUYUAN_CHART_PATHS_EMITTED.add(chart_path)
            print(f'CHART_SAVED:{chart_path}')
    except Exception:
        pass

# ===== 字体注册 =====
from matplotlib import font_manager
from matplotlib.figure import Figure
from matplotlib.text import Text
import matplotlib.pyplot as plt

_SUYUAN_FONT_PROP = None
_SUYUAN_FONT_NAME = None
_SUYUAN_FONT_FAMILY_CHAIN = ['Noto Sans CJK JP', 'Noto Sans CJK SC', 'Droid Sans Fallback', 'DejaVu Sans', 'sans-serif']
_suyuan_original_figure_savefig = Figure.savefig

def _suyuan_apply_chinese_font_config(fig=None):
    '''强制应用后端中文字体策略，忽略用户代码中的字体覆盖。'''
    try:
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = list(_SUYUAN_FONT_FAMILY_CHAIN)
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['mathtext.fontset'] = 'dejavusans'
        plt.rcParams['mathtext.default'] = 'it'
    except Exception:
        pass

    if fig is not None and _SUYUAN_FONT_PROP is not None:
        try:
            for text_obj in fig.findobj(match=Text):
                try:
                    text_obj.set_fontproperties(_SUYUAN_FONT_PROP)
                except Exception:
                    pass
        except Exception:
            pass
    return fig

def _suyuan_patched_figure_savefig(self, fname, *args, **kwargs):
    _suyuan_apply_chinese_font_config(self)
    result = _suyuan_original_figure_savefig(self, fname, *args, **kwargs)
    _suyuan_emit_chart_saved(fname)
    return result

if getattr(Figure.savefig, '__name__', '') != '_suyuan_patched_figure_savefig':
    Figure.savefig = _suyuan_patched_figure_savefig

# ===== 政府报告图表模板（自动注入） =====
_SUYUAN_GOVERNMENT_REPORT_STYLE_APPLIED = False

def _suyuan_axes_list(axes):
    if axes is None:
        return []
    if isinstance(axes, (list, tuple)):
        items = []
        for item in axes:
            items.extend(_suyuan_axes_list(item))
        return items
    if hasattr(axes, 'flat'):
        try:
            return [ax for ax in axes.flat if ax is not None]
        except Exception:
            pass
    return [axes]

def apply_government_report_style(fig=None, axes=None):
    '''应用政府报告图表默认样式。'''
    global _SUYUAN_GOVERNMENT_REPORT_STYLE_APPLIED
    style_rcparams = {
        'figure.figsize': [10.5, 6.2],
        'figure.dpi': 120,
        'savefig.dpi': 220,
        'savefig.facecolor': 'white',
        'savefig.bbox': 'tight',
        'axes.titlesize': 16,
        'axes.titleweight': 'semibold',
        'axes.labelsize': 13,
        'axes.labelweight': 'normal',
        'axes.labelpad': 6,
        'axes.titlepad': 12,
        'axes.grid': True,
        'axes.axisbelow': True,
        'axes.linewidth': 0.9,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'grid.alpha': 0.22,
        'grid.linestyle': '--',
        'grid.linewidth': 0.6,
        'legend.fontsize': 11,
        'legend.frameon': False,
        'lines.linewidth': 2.0,
        'lines.markersize': 5,
        'xtick.labelsize': 11,
        'ytick.labelsize': 11,
        'xtick.direction': 'out',
        'ytick.direction': 'out',
        'patch.linewidth': 0.5,
        'patch.edgecolor': 'white',
    }
    plt.rcParams.update(style_rcparams)

    for ax in _suyuan_axes_list(axes):
        try:
            ax.set_axisbelow(True)
            ax.grid(True, alpha=0.22, linestyle='--', linewidth=0.6)
            ax.tick_params(axis='both', labelsize=11, length=3, width=0.8)
            for spine_name in ('top', 'right'):
                if spine_name in ax.spines:
                    ax.spines[spine_name].set_visible(False)
        except Exception:
            pass

    if fig is not None:
        try:
            _suyuan_apply_chinese_font_config(fig)
            fig.set_facecolor('white')
            fig.tight_layout()
        except Exception:
            pass

    return fig, axes

def _suyuan_patch_subplots():
    if getattr(plt, '_suyuan_government_subplots_patched', False):
        return
    plt._suyuan_government_subplots_patched = True
    plt._suyuan_original_subplots = plt.subplots

    def _suyuan_report_subplots(*args, **kwargs):
        kwargs.setdefault('figsize', (10.5, 6.2))
        kwargs.setdefault('dpi', 120)
        kwargs.setdefault('constrained_layout', True)
        fig, axes = plt._suyuan_original_subplots(*args, **kwargs)
        apply_government_report_style(fig, axes)
        return fig, axes

    plt.subplots = _suyuan_report_subplots

_suyuan_patch_subplots()

# ===== 图表保存辅助函数（自动注入） =====
def save_chart(fig, filename, dpi=220, bbox_inches='tight', facecolor='white'):
    '''
    保存图表并触发前端缓存(自动通过ImageCache生成URL)

    Args:
        fig: matplotlib图表对象
        filename: 文件名(如 'chart.png')
        dpi: 分辨率(默认220)
        bbox_inches: 边界框(默认'tight')
        facecolor: 背景色(默认'white')

    Returns:
        str: 保存的文件路径

    Example:
        >>> import matplotlib.pyplot as plt
        >>> fig, ax = plt.subplots()
        >>> ax.plot([1, 2, 3], [1, 4, 9])
        >>> save_chart(fig, 'my_chart.png')  # 自动生成 /api/image/xxx URL
    '''
    # 确保图表目录存在
    charts_dir = __SUYUAN_IMAGES_DIR__
    try:
        os.makedirs(charts_dir, exist_ok=True)
    except PermissionError:
        # 如果默认目录无权限，使用临时目录
        import tempfile
        charts_dir = tempfile.gettempdir()
        os.makedirs(charts_dir, exist_ok=True)

    # 构建完整路径
    filepath = os.path.join(charts_dir, filename)

    # 保存图表。优先使用原始 savefig，避免自动拦截层重复输出标记。
    _suyuan_apply_chinese_font_config(fig)
    savefig_func = globals().get('_suyuan_original_figure_savefig')
    if savefig_func:
        savefig_func(fig, filepath, dpi=dpi, bbox_inches=bbox_inches, facecolor=facecolor)
    else:
        fig.savefig(filepath, dpi=dpi, bbox_inches=bbox_inches, facecolor=facecolor)

    # 关键：输出标准格式标记，触发 ImageCache 缓存
    _suyuan_emit_chart_saved(filepath)

    return filepath

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
            _SUYUAN_FONT_PROP = _font_prop
            _SUYUAN_FONT_NAME = _font_name
            _SUYUAN_FONT_FAMILY_CHAIN = [_font_name, 'Noto Sans CJK JP', 'Droid Sans Fallback', 'DejaVu Sans', 'sans-serif']
            _suyuan_apply_chinese_font_config()

            # 配置matplotlib的mathtext以支持LaTeX格式上下标
            # 注意：由于中文字体不支持LaTeX数学符号，系统会自动将Unicode下标转换为简写格式
            # 例如：PM2.5，ug/m3
            # 这样可以避免LaTeX与中文混合导致的显示问题
            # 如果需要严格科学符号，可以手动使用LaTeX格式（但要确保不与中文混合）
            plt.rcParams['mathtext.fontset'] = 'dejavusans'  # 使用dejavu字体渲染数学公式
            plt.rcParams['mathtext.default'] = 'it'  # 数学公式默认斜体（更符合数学符号惯例）

            # 确保中文字体和数学符号字体共存
            # 中文字体用于普通文本，mathtext用于数学符号
            # 政府报告默认字号：偏大、偏稳，保证投屏/打印可读性
            plt.rcParams['figure.figsize'] = [10.5, 6.2]
            plt.rcParams['figure.dpi'] = 120
            plt.rcParams['savefig.dpi'] = 220
            plt.rcParams['savefig.facecolor'] = 'white'
            plt.rcParams['savefig.bbox'] = 'tight'
            plt.rcParams['axes.titlesize'] = 16  # 标题字体大小
            plt.rcParams['axes.titleweight'] = 'semibold'
            plt.rcParams['axes.labelsize'] = 13  # 轴标签字体大小
            plt.rcParams['axes.labelweight'] = 'normal'
            plt.rcParams['axes.labelpad'] = 6
            plt.rcParams['axes.titlepad'] = 12
            plt.rcParams['axes.grid'] = True
            plt.rcParams['axes.axisbelow'] = True
            plt.rcParams['axes.linewidth'] = 0.9
            plt.rcParams['axes.spines.top'] = False
            plt.rcParams['axes.spines.right'] = False
            plt.rcParams['grid.alpha'] = 0.22
            plt.rcParams['grid.linestyle'] = '--'
            plt.rcParams['grid.linewidth'] = 0.6
            plt.rcParams['legend.fontsize'] = 11  # 图例字体大小
            plt.rcParams['legend.frameon'] = False
            plt.rcParams['lines.linewidth'] = 2.0
            plt.rcParams['lines.markersize'] = 5
            plt.rcParams['xtick.labelsize'] = 11
            plt.rcParams['ytick.labelsize'] = 11
            plt.rcParams['xtick.direction'] = 'out'
            plt.rcParams['ytick.direction'] = 'out'
            plt.rcParams['patch.linewidth'] = 0.5
            plt.rcParams['patch.edgecolor'] = 'white'
            # 注意：不使用 text.usetex=True，因为需要安装完整的LaTeX系统，速度较慢

            _font_registered = True
            break
        except Exception:
            pass

# ✅ 回退机制：如果字体文件注册失败，使用系统中已知的中文字体名称
if not _font_registered:
    # 使用系统已安装的 Noto Sans CJK 字体（支持中文和数字）
    _SUYUAN_FONT_PROP = None
    _SUYUAN_FONT_NAME = None
    _SUYUAN_FONT_FAMILY_CHAIN = ['Noto Sans CJK JP', 'Noto Sans CJK SC', 'Droid Sans Fallback', 'DejaVu Sans', 'sans-serif']
    _suyuan_apply_chinese_font_config()
    plt.rcParams['figure.figsize'] = [10.5, 6.2]
    plt.rcParams['figure.dpi'] = 120
    plt.rcParams['savefig.dpi'] = 220
    plt.rcParams['savefig.facecolor'] = 'white'
    plt.rcParams['savefig.bbox'] = 'tight'
    plt.rcParams['axes.titlesize'] = 16
    plt.rcParams['axes.titleweight'] = 'semibold'
    plt.rcParams['axes.labelsize'] = 13
    plt.rcParams['axes.labelweight'] = 'normal'
    plt.rcParams['axes.labelpad'] = 6
    plt.rcParams['axes.titlepad'] = 12
    plt.rcParams['axes.grid'] = True
    plt.rcParams['axes.axisbelow'] = True
    plt.rcParams['axes.linewidth'] = 0.9
    plt.rcParams['axes.spines.top'] = False
    plt.rcParams['axes.spines.right'] = False
    plt.rcParams['grid.alpha'] = 0.22
    plt.rcParams['grid.linestyle'] = '--'
    plt.rcParams['grid.linewidth'] = 0.6
    plt.rcParams['legend.fontsize'] = 11
    plt.rcParams['legend.frameon'] = False
    plt.rcParams['lines.linewidth'] = 2.0
    plt.rcParams['lines.markersize'] = 5
    plt.rcParams['xtick.labelsize'] = 11
    plt.rcParams['ytick.labelsize'] = 11
    plt.rcParams['xtick.direction'] = 'out'
    plt.rcParams['ytick.direction'] = 'out'
    plt.rcParams['patch.linewidth'] = 0.5
    plt.rcParams['patch.edgecolor'] = 'white'

# ===== 字体注册完成 =====

""".replace("__SUYUAN_IMAGES_DIR__", images_dir_literal)

        lines = code.split('\n')
        modified_lines = [font_registration_code]

        # 步骤2：处理每一行，删除错误的字体设置
        for line in lines:
            # 检测并删除错误的字体设置（已在注册代码中统一配置）
            # 同时检测 plt.rcParams 和 matplotlib.rcParams，以及可能覆盖中文字体的字体设置。
            has_font_setting = (
                ("font.sans-serif" in line or "font.family" in line)
                and ("plt.rcParams" in line or "matplotlib.rcParams" in line)
            ) or (
                "axes.unicode_minus" in line and ("plt.rcParams" in line or "matplotlib.rcParams" in line)
            )

            if has_font_setting:
                logger.debug("font_setting_removed", original_line=line.strip())
                continue  # 跳过这行，不添加到结果中
            else:
                modified_lines.append(line)

        # 步骤3：拼接代码
        injected_code = '\n'.join(modified_lines)

        # 步骤4：自动转换Unicode下标/上标字符为LaTeX格式
        injected_code = self._convert_unicode_subscript_to_latex(injected_code)

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
            # WORD_SAVED:/path/to/file.docx, WORD_REPORT_SAVED:/path/to/file.docx, EXCEL_SAVED:/path/to/file.xlsx
            r'(?:WORD_SAVED|WORD_REPORT_SAVED|DOCX_SAVED|PPT_SAVED|PPTX_SAVED|PDF_SAVED|EXCEL_SAVED|HTML_REPORT_SAVED)[:：]\s*(.+?\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt|html|htm))',
            # 报告已生成：/path/to/文件名.docx
            r'(?:报告已生成|文件已保存|已生成|保存成功|File saved|saved)[:：]\s*(.+?\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt|html|htm))',
            # 文件名.xlsx（带中文的后缀）
            r'(.+?\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt|html|htm))\s*[已]*[保存生成]*',
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
                "执行 Python 代码，用于数据处理、数值计算、可视化、Excel处理和中间资源生成。"
                "助手Agent和社交Agent在处理复杂 Python、Excel、图表或文件生成前，"
                "必须先阅读 backend/app/tools/utility/execute_python_manual.md。"
                "正式报告最终交付必须优先使用 create_report_package："
                "先准备 report.qmd 内容和真实资源路径，再由 create_report_package 复制资源、规范化报告包内相对路径并触发右侧面板预览；"
                "HTML/Word/PPT/QMD下载和HTML分享链接由前端右侧面板调用固定后端报告API处理。"
                "不要把 execute_python 作为正式报告最终交付工具，也不要在 Python 脚本里手写正式报告格式转换。"
                "演讲材料、展示页、数据大屏、交互网页或可视化叙事等非正式报告，应使用 create_html_artifact 收口，"
                "右侧面板仅提供HTML预览、下载HTML和分享链接。"
                "只有用户明确要求一次性 Word/Office 文件且不需要 qmd/HTML/PPT 同源报告包时，才直接生成 Office 文件。"
                "优先使用专用统计/查询工具；只有专用工具无法满足自定义计算时再使用本工具。"
                "使用工具返回的 data_id/report_data_id 计算前必须先调用 read_data_registry 读取数据；"
                "execute_python 的 get_raw_data 只返回 read_data_registry 已读取的数据快照，未读取会报错；"
                "不要在代码中绕过 read_data_registry 直接导入 data_registry 或 backend_data_registry。"
                "执行 matplotlib 画图时，系统会自动注入政府报告图表模板，默认把字号、画布、网格和导出分辨率调大。"
                "matplotlib 中文字体由系统自动注入并在保存图片前强制应用；代码中不要指定字体文件、FontProperties、font.family、font.sans-serif 或 fontfamily。"
                "使用 Python 绘制图表时，默认一张图片只包含一个核心图表/分析问题；"
                "除非用户明确要求多子图、组合图、仪表盘或一页多图对比，不要使用 subplot/subplots/多 Axes 把多个图表拼到同一张图片。"
                "同一数据源需要多个分析视角时，优先选择最相关的一张图；确需多图则分别保存为多个图片文件。"
                "政府报告图片默认使用较大字号和较高分辨率，避免标题、坐标轴和图例过小。"
                "生成中间文件保存到 backend_data_registry，并打印输出路径供后续工具使用。默认超时30秒。"
                "输出artifact schema：files为生成文件列表，file_path为主文件；"
                "Office/PDF返回pdf_preview，Notebook返回html_preview，"
                "轻量HTML兼容流程可使用save_html_report()，正式报告不要优先使用该流程，"
                "图片/ECharts返回visuals。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "要执行的 Python 代码。涉及 matplotlib/seaborn/plotly 静态出图时，"
                            "默认每个输出图片只包含一个核心图表；除非用户明确要求多子图/组合图，"
                            "不要使用 subplot/subplots/多 Axes 在单张图片中拼接多个图表。政府报告图片默认会注入更大的字号、画布和更高分辨率；"
                            "中文字体由系统自动接管，代码不要指定 FontProperties、font.family、font.sans-serif 或 fontfamily。"
                        )
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒），默认30"
                    }
                },
                "required": ["code"]
            }
        }
