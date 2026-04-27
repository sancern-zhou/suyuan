"""
生成可分享的Notebook HTML文件
"""
import json
import base64
from pathlib import Path
from typing import Dict, Any
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class GenerateShareableNotebookTool(LLMTool):
    """生成可分享的Notebook HTML工具"""

    def __init__(self):
        super().__init__(
            name="generate_shareable_notebook",
            description="""
            生成可分享的Jupyter Notebook HTML文件（用于外部分享）

            使用场景：
            - 用户点击"分享"按钮时生成HTML
            - 生成包含完整内容的独立HTML文件
            - 支持移动端和桌面端响应式显示

            参数：
            - notebook_path: Notebook文件路径（.ipynb）
            - output_name: 输出HTML文件名（不含扩展名，可选）

            返回：
            - share_link: 分享链接（外网可访问）
            - html_path: HTML文件路径
            """,
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

    async def execute(self, notebook_path: str, output_name: str = None) -> Dict[str, Any]:
        """
        生成可分享的HTML文件

        Args:
            notebook_path: Notebook文件路径
            output_name: 输出文件名（可选）

        Returns:
            {
                "success": True,
                "data": {
                    "share_link": "http://219.135.180.51:56041/reports/xxx_share.html",
                    "html_path": "/path/to/html"
                },
                "summary": "已生成分享链接"
            }
        """
        try:
            from config.settings import settings

            notebook_path = Path(notebook_path)

            if not notebook_path.exists():
                return {
                    "success": False,
                    "data": {},
                    "summary": f"Notebook文件不存在: {notebook_path}"
                }

            # 读取Notebook
            with open(notebook_path, 'r', encoding='utf-8') as f:
                notebook = json.load(f)

            # 生成HTML主体（Notebook中的URL已经是外网地址，无需替换）
            html_body = await self._convert_notebook_to_html(notebook, notebook_path)

            # 包装响应式样式
            html_content = self._wrap_with_responsive_styles(html_body)

            # 确定输出路径
            if output_name is None:
                output_name = notebook_path.stem  # 不含扩展名的文件名

            output_dir = Path("frontend/public/reports")
            output_dir.mkdir(parents=True, exist_ok=True)

            output_path = output_dir / f"{output_name}_share.html"

            # 保存HTML文件
            output_path.write_text(html_content, encoding='utf-8')

            # 生成分享链接（使用外网URL）
            share_link = f"{settings.frontend_base_url}/reports/{output_name}_share.html"

            logger.info(
                "生成分享HTML成功",
                notebook_path=str(notebook_path),
                output_path=str(output_path),
                share_link=share_link
            )

            return {
                "success": True,
                "data": {
                    "share_link": share_link,
                    "html_path": str(output_path)
                },
                "summary": f"已生成分享链接: {share_link}"
            }

        except Exception as e:
            logger.error("生成分享HTML失败", error=str(e), exc_info=True)
            return {
                "success": False,
                "data": {},
                "summary": f"生成失败: {str(e)}"
            }

    async def _convert_notebook_to_html(self, notebook: dict, notebook_path: Path) -> str:
        """
        将Notebook转换为HTML主体

        Args:
            notebook: Notebook字典
            notebook_path: Notebook文件路径（用于解析图片路径）

        Returns:
            HTML字符串
        """
        cells_html = []

        for cell in notebook.get('cells', []):
            cell_type = cell.get('cell_type', 'code')
            source = self._normalize_source(cell.get('source', ''))
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
                    <div class="input-area">
                        <span class="input-prompt">In:</span>
                        <pre><code>{self._escape_html(source)}</code></pre>
                    </div>
                ''')

                # 输出区域
                if outputs:
                    output_html = '<div class="output-area">'

                    for output in outputs:
                        # 文本输出
                        if 'text' in output:
                            output_html += f'<pre class="output-text">{self._escape_html(output["text"])}</pre>'

                        # 数据输出（图片等）
                        if 'data' in output:
                            data = output['data']

                            # PNG图片
                            if 'image/png' in data:
                                # 尝试从本地文件读取并转为base64
                                img_b64 = await self._get_image_base64(
                                    output,
                                    notebook_path
                                )
                                if img_b64:
                                    output_html += f'<img src="data:image/png;base64,{img_b64}" />'
                                else:
                                    # 使用原始base64数据
                                    output_html += f'<img src="data:image/png;base64,{data["image/png"]}" />'

                            # JPEG图片
                            elif 'image/jpeg' in data:
                                img_b64 = await self._get_image_base64(
                                    output,
                                    notebook_path
                                )
                                if img_b64:
                                    output_html += f'<img src="data:image/jpeg;base64,{img_b64}" />'
                                else:
                                    output_html += f'<img src="data:image/jpeg;base64,{data["image/jpeg"]}" />'

                            # 纯文本
                            elif 'text/plain' in data:
                                output_html += f'<pre class="output-text">{self._escape_html(data["text/plain"])}</pre>'

                    output_html += '</div>'
                    cells_html.append(output_html)

                cells_html.append('</div>')

        return ''.join(cells_html)

    async def _get_image_base64(self, output: dict, notebook_path: Path) -> str:
        """
        尝试从本地文件读取图片并转为base64

        Args:
            output: 输出字典
            notebook_path: Notebook文件路径

        Returns:
            base64编码的图片字符串，如果失败返回空字符串
        """
        try:
            # 尝试从metadata获取图片文件名
            metadata = output.get('metadata', {})
            filename = metadata.get('filename', metadata.get('filenames', [''])[0])

            if not filename:
                return ''

            # 尝试在reports目录查找图片
            reports_dir = notebook_path.parent.parent / "reports"
            if reports_dir.exists():
                img_path = reports_dir / filename
                if img_path.exists():
                    with open(img_path, 'rb') as f:
                        img_data = f.read()
                    return base64.b64encode(img_data).decode('utf-8')

            # 尝试在notebook同目录查找
            img_path = notebook_path.parent / filename
            if img_path.exists():
                with open(img_path, 'rb') as f:
                    img_data = f.read()
                return base64.b64encode(img_data).decode('utf-8')

            return ''

        except Exception as e:
            logger.warning("读取本地图片失败", filename=filename, error=str(e))
            return ''

    def _normalize_source(self, source) -> str:
        """规范化source字段为字符串"""
        if isinstance(source, list):
            return ''.join(source)
        elif isinstance(source, str):
            return source
        else:
            return str(source)

    def _markdown_to_html(self, text: str) -> str:
        """
        简单的markdown转HTML

        Args:
            text: Markdown文本

        Returns:
            HTML字符串
        """
        html = text

        # 标题
        html = html.replace('### ', '<h3>').replace('\n', '</h3>\n', 1)
        html = html.replace('## ', '<h2>').replace('\n', '</h2>\n', 1)
        html = html.replace('# ', '<h1>').replace('\n', '</h1>\n', 1)

        # 粗体和斜体
        html = html.replace('**', '<strong>').replace('**', '</strong>')
        html = html.replace('*', '<em>').replace('*', '</em>')

        # 链接
        html = html.replace('[', '<a href="').replace('](', '">').replace(')', '</a>')

        # 图片
        html = html.replace('![](', '<img src="').replace(')', '">')

        # 段落
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

    def _wrap_with_responsive_styles(self, body: str) -> str:
        """包装响应式样式"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>分析报告</title>
    <style>
        /* 全局样式 */
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 16px;
            background: #f5f5f5;
            color: #333;
        }}

        /* 容器 */
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 32px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        /* 单元格 */
        .cell {{
            margin-bottom: 24px;
            padding: 16px;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            background: white;
        }}

        .markdown-cell {{
            border-left: 3px solid #4CAF50;
            background: #f9f9f9;
        }}

        .code-cell {{
            border-left: 3px solid #2196F3;
        }}

        /* 输入区域 */
        .input-area {{
            margin-bottom: 12px;
        }}

        .input-prompt {{
            color: #303F9F;
            font-weight: bold;
            font-family: "Courier New", monospace;
            font-size: 14px;
        }}

        /* 输出区域 */
        .output-area {{
            margin-top: 12px;
            padding: 12px;
            background: #f8f8f8;
            border-radius: 4px;
            border-left: 3px solid #D32F2F;
        }}

        .output-prompt {{
            color: #D32F2F;
            font-weight: bold;
            font-family: "Courier New", monospace;
        }}

        /* 代码和文本 */
        pre {{
            background: #f5f5f5;
            padding: 12px;
            border-radius: 4px;
            overflow-x: auto;
            font-family: "Courier New", monospace;
            font-size: 13px;
            line-height: 1.5;
            margin: 8px 0;
        }}

        code {{
            font-family: "Courier New", monospace;
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 13px;
        }}

        .output-text {{
            background: white;
            margin: 0;
        }}

        /* 图片响应式 */
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 16px 0;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        /* Markdown内容 */
        .markdown-content h1,
        .markdown-content h2,
        .markdown-content h3,
        .markdown-content h4,
        .markdown-content h5,
        .markdown-content h6 {{
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            color: #333;
            font-weight: 600;
        }}

        .markdown-content h1 {{
            font-size: 2em;
            border-bottom: 2px solid #eee;
            padding-bottom: 0.3em;
        }}

        .markdown-content h2 {{
            font-size: 1.5em;
            border-bottom: 1px solid #eee;
            padding-bottom: 0.3em;
        }}

        .markdown-content h3 {{
            font-size: 1.25em;
        }}

        .markdown-content p {{
            margin: 1em 0;
        }}

        .markdown-content ul,
        .markdown-content ol {{
            padding-left: 2em;
            margin: 1em 0;
        }}

        .markdown-content li {{
            margin: 0.5em 0;
        }}

        /* 移动端适配 */
        @media (max-width: 768px) {{
            body {{
                padding: 0;
                background: white;
            }}

            .container {{
                padding: 16px;
                border-radius: 0;
                box-shadow: none;
            }}

            .cell {{
                padding: 12px;
                margin-bottom: 16px;
            }}

            pre {{
                font-size: 12px;
                padding: 8px;
            }}

            code {{
                font-size: 12px;
            }}

            .markdown-content h1 {{
                font-size: 1.5em;
            }}

            .markdown-content h2 {{
                font-size: 1.25em;
            }}

            .markdown-content h3 {{
                font-size: 1.1em;
            }}

            img {{
                margin: 12px 0;
            }}
        }}

        /* 超小屏幕适配 */
        @media (max-width: 480px) {{
            .container {{
                padding: 12px;
            }}

            .cell {{
                padding: 8px;
            }}

            pre {{
                font-size: 11px;
                padding: 6px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        {body}
    </div>
</body>
</html>"""
