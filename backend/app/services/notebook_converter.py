"""
Notebook HTML conversion service
Convert Jupyter Notebook (.ipynb) to HTML for frontend preview
"""
from pathlib import Path
import tempfile
import shutil
import uuid
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class NotebookConverter:
    """Convert Jupyter Notebook to HTML"""

    def __init__(self):
        self.output_dir = Path(tempfile.gettempdir()) / "notebook_html_cache"
        self.output_dir.mkdir(exist_ok=True)

    async def convert_to_html(self, notebook_path: str) -> Dict[str, Any]:
        """
        Convert Jupyter Notebook to HTML

        Args:
            notebook_path: Path to the .ipynb file

        Returns:
            {
                "html_id": "unique-id",
                "html_path": "/path/to/html",
                "html_url": "/api/notebook/html/{html_id}",
                "pages": 13,  # 单元格数量
                "cells": 13,
                "size": 12345
            }
        """
        try:
            html_id = f"{uuid.uuid4()}"
            html_path = self.output_dir / f"{html_id}.html"

            # 读取notebook文件
            import json
            with open(notebook_path, 'r', encoding='utf-8') as f:
                nb = json.load(f)

            # 使用nbconvert转换为HTML
            try:
                from nbconvert import HTMLExporter
                import nbformat

                # 读取原始JSON并规范化
                with open(notebook_path, 'r', encoding='utf-8') as f:
                    nb_dict = json.load(f)

                # 规范化notebook字典（在转换为NotebookNode之前）
                nb_dict = self._normalize_notebook_dict(nb_dict)

                # 从规范化后的字典创建NotebookNode
                nb_obj = nbformat.from_dict(nb_dict)

                # 验证并修复notebook（使用relax模式）
                try:
                    nbformat.validate(nb_obj, relax_add_props=True)
                except Exception as e:
                    logger.warning(f"notebook_validation_failed_relaxing: {e}")
                    # 验证失败，尝试进一步修复
                    nb_obj = self._deep_normalize_notebook(nb_obj)

                # 配置HTML导出器
                html_exporter = HTMLExporter(
                    template_name='classic',
                    exclude_input_prompt=False,
                    exclude_output_prompt=False,
                    exclude_input=False,
                    exclude_output=False,
                    # 禁用预处理器验证（避免验证错误）
                    preprocessors=[]
                )

                # 转换为HTML
                (body, resources) = html_exporter.from_notebook_node(nb_obj)

                # 添加响应式样式
                html_content = self._wrap_with_styles(body)

            except ImportError:
                # nbconvert未安装，使用简单转换
                logger.warning("nbconvert_not_installed_using_simple_conversion")
                html_content = self._simple_notebook_to_html(nb)

            # 保存HTML文件
            html_path.write_text(html_content, encoding='utf-8')

            return {
                "html_id": html_id,
                "html_path": str(html_path),
                "html_url": f"/api/notebook/html/{html_id}",
                "pages": len(nb.get('cells', [])),
                "cells": len(nb.get('cells', [])),
                "size": html_path.stat().st_size
            }

        except Exception as e:
            logger.error(f"Notebook conversion error: {e}", exc_info=True)
            raise

    def _wrap_with_styles(self, body: str) -> str:
        """添加响应式样式和完整HTML结构"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jupyter Notebook Preview</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .cell {{
            margin-bottom: 20px;
            padding: 15px;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
        }}
        .input_area {{
            margin-bottom: 10px;
        }}
        .input_prompt {{
            color: #303F9F;
            font-weight: bold;
            font-family: monospace;
        }}
        .output_area {{
            margin-top: 10px;
            padding: 10px;
            background: #f8f8f8;
            border-radius: 4px;
        }}
        .output_prompt {{
            color: #D32F2F;
            font-weight: bold;
            font-family: monospace;
        }}
        pre {{
            background: #f8f8f8;
            padding: 12px;
            border-radius: 4px;
            overflow-x: auto;
            font-family: monospace;
            font-size: 13px;
        }}
        code {{
            font-family: monospace;
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
        }}
        img {{
            max-width: 100%;
            height: auto;
        }}
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}
        .markdown-cell {{
            border-left: 3px solid #4CAF50;
        }}
        .code-cell {{
            border-left: 3px solid #2196F3;
        }}
    </style>
</head>
<body>
    <div class="container">
        {body}
    </div>
</body>
</html>"""

    def _normalize_notebook(self, nb_obj) -> object:
        """
        规范化notebook对象，确保符合nbformat v4规范

        主要修复：
        - 确保所有code单元格都有outputs字段
        - 确保所有code单元格都有execution_count字段
        - 确保所有单元格都有metadata字段
        - 确保source是字符串而不是列表

        Args:
            nb_obj: nbformat.NotebookNode对象

        Returns:
            规范化后的notebook对象
        """
        # 遍历所有单元格，规范化格式
        for cell in nb_obj.cells:
            # 确保metadata字段存在
            if not hasattr(cell, 'metadata') or cell.metadata is None:
                cell.metadata = {}

            # 对于code单元格，确保必需字段存在
            if cell.cell_type == 'code':
                # 确保outputs字段存在
                if not hasattr(cell, 'outputs') or cell.outputs is None:
                    cell.outputs = []

                # 确保execution_count字段存在
                if not hasattr(cell, 'execution_count'):
                    # 如果有outputs但没有execution_count，尝试推断
                    if cell.outputs and any(cell.outputs):
                        # 有输出，说明已执行，设置execution_count
                        cell.execution_count = None  # None表示已执行但计数未知
                    else:
                        # 无输出，说明未执行或不需要执行
                        cell.execution_count = None
                elif cell.execution_count is None:
                    # 已经有execution_count但为None，保持不变
                    pass

            # 确保source是字符串（nbformat v4要求）
            if hasattr(cell, 'source') and isinstance(cell.source, list):
                cell.source = ''.join(cell.source)

        return nb_obj

    def _normalize_notebook_dict(self, nb_dict: dict) -> dict:
        """
        在字典层面规范化notebook（在转换为NotebookNode之前）

        Args:
            nb_dict: notebook字典

        Returns:
            规范化后的notebook字典
        """
        # 规范化单元格
        cells = nb_dict.get('cells', [])
        normalized_cells = []

        for cell in cells:
            if cell.get('cell_type') == 'code':
                # 确保code单元格有所有必需字段
                normalized_cell = {
                    'cell_type': 'code',
                    'source': self._normalize_source(cell.get('source', '')),
                    'metadata': cell.get('metadata', {}),
                    'outputs': cell.get('outputs', []),
                    'execution_count': cell.get('execution_count', None)
                }
                normalized_cells.append(normalized_cell)
            else:
                # markdown或其他类型
                normalized_cell = {
                    'cell_type': cell.get('cell_type', 'markdown'),
                    'source': self._normalize_source(cell.get('source', '')),
                    'metadata': cell.get('metadata', {})
                }
                normalized_cells.append(normalized_cell)

        nb_dict['cells'] = normalized_cells
        return nb_dict

    def _normalize_source(self, source) -> str:
        """规范化source字段为字符串"""
        if isinstance(source, list):
            return ''.join(source)
        elif isinstance(source, str):
            return source
        else:
            return str(source)

    def _deep_normalize_notebook(self, nb_obj) -> object:
        """
        深度规范化NotebookNode对象（验证失败时使用）

        Args:
            nb_obj: nbformat.NotebookNode对象

        Returns:
            深度规范化后的notebook对象
        """
        import nbformat

        # 重新创建notebook，确保所有字段都符合规范
        normalized_cells = []

        for cell in nb_obj.cells:
            if cell.cell_type == 'code':
                # 创建新的code单元格，确保所有字段都存在
                new_cell = nbformat.v4.new_code_cell()
                new_cell.source = self._normalize_source(getattr(cell, 'source', ''))
                new_cell.outputs = getattr(cell, 'outputs', [])

                # execution_count：如果有设置则保留，否则为None
                if hasattr(cell, 'execution_count') and cell.execution_count is not None:
                    new_cell.execution_count = cell.execution_count
                # 不设置execution_count，让nbformat处理

                # 保留metadata
                if hasattr(cell, 'metadata') and cell.metadata:
                    new_cell.metadata = cell.metadata

                normalized_cells.append(new_cell)
            else:
                # markdown或raw单元格
                if cell.cell_type == 'markdown':
                    new_cell = nbformat.v4.new_markdown_cell()
                else:
                    new_cell = nbformat.v4.new_raw_cell(cell.cell_type)

                new_cell.source = self._normalize_source(getattr(cell, 'source', ''))
                if hasattr(cell, 'metadata') and cell.metadata:
                    new_cell.metadata = cell.metadata

                normalized_cells.append(new_cell)

        # 创建新的notebook对象
        normalized_nb = nbformat.v4.new_notebook(cells=normalized_cells)
        normalized_nb.metadata = getattr(nb_obj, 'metadata', {})
        normalized_nb.nbformat = getattr(nb_obj, 'nbformat', 4)
        normalized_nb.nbformat_minor = getattr(nb_obj, 'nbformat_minor', 2)

        return normalized_nb

    def _simple_notebook_to_html(self, nb: dict) -> str:
        """简单的notebook转HTML（nbconvert未安装时使用）"""
        cells_html = []

        for cell in nb.get('cells', []):
            cell_type = cell.get('cell_type', 'code')
            source = cell.get('source', '')
            outputs = cell.get('outputs', [])

            if cell_type == 'markdown':
                # Markdown单元格
                cells_html.append(f'''
                <div class="cell markdown-cell">
                    <div class="markdown-content">
                        {self._markdown_to_html(source)}
                    </div>
                </div>
                ''')
            else:
                # 代码单元格
                cells_html.append(f'''
                <div class="cell code-cell">
                    <div class="input_area">
                        <span class="input_prompt">In:</span>
                        <pre><code>{self._escape_html(source)}</code></pre>
                    </div>
                ''')

                # 输出区域
                if outputs:
                    output_html = '<div class="output_area">'
                    output_html += '<span class="output_prompt">Out:</span>'

                    for output in outputs:
                        if 'text' in output:
                            output_html += f'<pre>{self._escape_html(output["text"])}</pre>'
                        elif 'data' in output:
                            data = output['data']
                            if 'image/png' in data:
                                output_html += f'<img src="data:image/png;base64,{data["image/png"]}" />'
                            elif 'text/plain' in data:
                                output_html += f'<pre>{self._escape_html(data["text/plain"])}</pre>'

                    output_html += '</div>'
                    cells_html.append(output_html)

                cells_html.append('</div>')

        return self._wrap_with_styles(''.join(cells_html))

    def _markdown_to_html(self, text: str) -> str:
        """简单的markdown转HTML"""
        # 基础markdown转换
        html = text
        html = html.replace('### ', '<h3>').replace('\n', '</h3>\n', 1)
        html = html.replace('## ', '<h2>').replace('\n', '</h2>\n', 1)
        html = html.replace('# ', '<h1>').replace('\n', '</h1>\n', 1)
        html = html.replace('**', '<strong>').replace('**', '</strong>')
        html = html.replace('*', '<em>').replace('*', '</em>')
        html = html.replace('\n\n', '</p><p>')
        html = f'<p>{html}</p>'
        return html

    def _escape_html(self, text: str) -> str:
        """转义HTML特殊字符"""
        if isinstance(text, list):
            text = ''.join(text)
        return (str(text)
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#x27;'))

    def cleanup_html(self, html_id: str) -> bool:
        """清理HTML缓存文件"""
        try:
            html_path = self.output_dir / f"{html_id}.html"
            if html_path.exists():
                html_path.unlink()
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to cleanup HTML {html_id}: {e}")
            return False

    def get_html_path(self, html_id: str) -> Path:
        """获取HTML文件路径"""
        return self.output_dir / f"{html_id}.html"

    def html_exists(self, html_id: str) -> bool:
        """检查HTML文件是否存在"""
        return self.get_html_path(html_id).exists()


# 全局单例
notebook_converter = NotebookConverter()
