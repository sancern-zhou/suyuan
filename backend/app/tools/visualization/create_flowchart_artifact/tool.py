"""Tool for creating previewable flowchart HTML artifacts."""
from __future__ import annotations

import html
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.tools.artifact_utils import attach_document_artifact
from app.services.html_artifact_service import html_artifact_service
from app.tools.base.tool_interface import LLMTool, ToolCategory


DOT_ID_PATTERN = re.compile(r"[^A-Za-z0-9_]")


def _sanitize_dot_id(raw_id: Any, index: int) -> str:
    text = DOT_ID_PATTERN.sub("_", str(raw_id or "")).strip("_")
    if not text:
        text = f"n{index + 1}"
    if text[0].isdigit():
        text = f"n_{text}"
    return text


def _escape_dot_label(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _shape_to_graphviz(shape: str) -> str:
    mapping = {
        "rect": "box",
        "rounded": "box",
        "diamond": "diamond",
        "circle": "circle",
        "stadium": "oval",
        "subroutine": "box3d",
    }
    return mapping.get(shape, "box")


class CreateFlowchartArtifactTool(LLMTool):
    """Create a previewable/shareable flowchart artifact rendered with Graphviz."""

    def __init__(self):
        super().__init__(
            name="create_flowchart_artifact",
            description=(
                "创建可预览的流程图 HTML 产物。"
                "默认使用 Graphviz 生成 SVG，适合传统上下布局、业务流程图、决策树和 Agent 执行流。"
                "工具会把图渲染为静态 SVG 并保存为 HTML 展示页，右侧面板可直接预览与分享。"
                "可选使用 Mermaid 作为显式兜底。"
            ),
            category=ToolCategory.VISUALIZATION,
            version="2.0.0",
        )
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "artifact_id": {
                        "type": "string",
                        "description": "流程图产物ID，只允许字母、数字、下划线、连字符；其他字符会自动转义。",
                    },
                    "title": {
                        "type": "string",
                        "description": "流程图标题。",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["TB", "BT", "LR", "RL"],
                        "description": "流程图方向。TB=自上而下，LR=自左向右。",
                    },
                    "layout_engine": {
                        "type": "string",
                        "enum": ["graphviz", "mermaid", "auto"],
                        "description": "布局引擎。默认 graphviz，mermaid 作为兜底。",
                    },
                    "mermaid": {
                        "type": "string",
                        "description": "直接提供 Mermaid flowchart 语法。仅在 layout_engine=mermaid 或 auto 且未提供 steps 时使用。",
                    },
                    "steps": {
                        "type": "array",
                        "description": "流程步骤列表。会自动转换为 Graphviz 节点。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "节点ID，可选。"},
                                "label": {"type": "string", "description": "节点显示文本。"},
                                "shape": {
                                    "type": "string",
                                    "enum": ["rect", "rounded", "diamond", "circle", "stadium", "subroutine"],
                                    "description": "节点形状。默认 rect。",
                                },
                                "group": {"type": "string", "description": "分组ID，可选。"},
                            },
                            "required": ["label"],
                        },
                    },
                    "edges": {
                        "type": "array",
                        "description": "连线列表。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string", "description": "起始节点ID。"},
                                "to": {"type": "string", "description": "目标节点ID。"},
                                "label": {"type": "string", "description": "连线文字，可选。"},
                                "style": {
                                    "type": "string",
                                    "enum": ["solid", "dashed"],
                                    "description": "连线样式。",
                                },
                            },
                            "required": ["from", "to"],
                        },
                    },
                    "notes": {
                        "type": "string",
                        "description": "补充说明，会写入 HTML 页尾。",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "额外元数据。",
                    },
                },
                "required": ["artifact_id", "title"],
            },
        }

    def _build_dot_from_steps(
        self,
        steps: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]],
        direction: str,
        title: str,
    ) -> str:
        rankdir = direction if direction in {"TB", "BT", "LR", "RL"} else "TB"
        dot_lines = [
            "digraph G {",
            '  graph [rankdir="%s", bgcolor="transparent", pad="0.25", nodesep="0.45", ranksep="0.8", splines="ortho", concentrate=true];' % rankdir,
            '  node [shape=box, style="rounded,filled", fontname="Microsoft YaHei", fontsize=12, margin="0.12,0.08", color="#9aa9c3", fillcolor="#ffffff", fontcolor="#18202f"];',
            '  edge [color="#5b6b82", penwidth=1.8, arrowsize=0.8, fontname="Microsoft YaHei", fontsize=10];',
            f'  label="{_escape_dot_label(title)}";',
            '  labelloc="t";',
            '  fontsize=18;',
            '  fontname="Microsoft YaHei";',
        ]

        if not steps:
            dot_lines.extend([
                '  empty [label="无步骤数据", shape=box, style="rounded,filled", fillcolor="#f6f7fb"];',
                '  hint [label="请提供 steps / edges 或 mermaid", shape=box, style="dashed", color="#c0cad8"];',
                "  empty -> hint;",
            ])
            dot_lines.append("}")
            return "\n".join(dot_lines)

        node_ids: Dict[str, str] = {}
        for idx, step in enumerate(steps):
            node_id = _sanitize_dot_id(step.get("id") or step.get("label"), idx)
            node_ids[str(step.get("id") or step.get("label") or node_id)] = node_id
            label = _escape_dot_label(step.get("label", node_id))
            shape = _shape_to_graphviz((step.get("shape") or "rect").lower())
            style = "rounded,filled" if shape in {"box", "oval", "box3d"} else "filled"
            fillcolor = step.get("fillcolor") or "#ffffff"
            color = step.get("color") or "#9aa9c3"
            if shape == "diamond":
                style = "filled"
                fillcolor = step.get("fillcolor") or "#fff8ec"
                color = step.get("color") or "#f0b44c"

            dot_lines.append(
                f'  {node_id} [label="{label}", shape="{shape}", style="{style}", fillcolor="{fillcolor}", color="{color}"];'
            )

        if edges:
            for edge in edges:
                src_key = str(edge.get("from") or "")
                dst_key = str(edge.get("to") or "")
                src = node_ids.get(src_key) or _sanitize_dot_id(src_key, 0)
                dst = node_ids.get(dst_key) or _sanitize_dot_id(dst_key, 0)
                label = _escape_dot_label(edge.get("label", ""))
                style = "dashed" if edge.get("style") == "dashed" else "solid"
                attrs = [f'style="{style}"']
                if label:
                    attrs.append(f'label="{label}"')
                    attrs.append('fontcolor="#6b7280"')
                dot_lines.append(f"  {src} -> {dst} [{', '.join(attrs)}];")
        else:
            ordered_ids = list(node_ids.values())
            for left, right in zip(ordered_ids, ordered_ids[1:]):
                dot_lines.append(f"  {left} -> {right};")

        dot_lines.append("}")
        return "\n".join(dot_lines)

    def _render_graphviz_svg(self, dot_source: str) -> str:
        result = subprocess.run(
            ["dot", "-Tsvg"],
            input=dot_source,
            text=True,
            capture_output=True,
            check=True,
        )
        svg = result.stdout.strip()
        svg_start = svg.find("<svg")
        if svg_start >= 0:
            svg = svg[svg_start:]
        return svg

    def _build_mermaid_html(self, title: str, mermaid: str, notes: str | None = None) -> str:
        notes_html = ""
        if notes:
            notes_html = f"<section class=\"notes\"><pre>{html.escape(str(notes))}</pre></section>"

        safe_mermaid = html.escape(mermaid)
        safe_title = html.escape(title)
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f6f7fb; color: #18202f; }}
    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
    .panel {{ background: #fff; border: 1px solid #d9e0ee; border-radius: 8px; padding: 20px; overflow: auto; }}
    .notes {{ margin-top: 16px; border-top: 1px solid #d9e0ee; padding-top: 12px; color: #5d677b; font-size: 13px; }}
    .notes pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
    .mermaid {{ min-height: 220px; }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>
    window.addEventListener('DOMContentLoaded', () => {{
      mermaid.initialize({{
        startOnLoad: true,
        securityLevel: 'loose',
        theme: 'default',
        flowchart: {{ useMaxWidth: true, htmlLabels: true }}
      }});
    }});
  </script>
</head>
<body>
  <div class="wrap">
    <h1>{safe_title}</h1>
    <div class="panel">
      <div class="mermaid">{safe_mermaid}</div>
      {notes_html}
    </div>
  </div>
</body>
</html>
"""

    def _build_graphviz_html(self, title: str, svg: str, notes: str | None = None) -> str:
        notes_html = ""
        if notes:
            notes_html = f"<section class=\"notes\"><pre>{html.escape(str(notes))}</pre></section>"

        safe_title = html.escape(title)
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7fb;
      --panel: #ffffff;
      --text: #18202f;
      --muted: #5d677b;
      --border: #d9e0ee;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); }}
    .wrap {{ max-width: 1600px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 12px; font-size: 24px; line-height: 1.2; }}
    .hint {{ color: var(--muted); font-size: 13px; margin-bottom: 16px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 20px; overflow: auto; }}
    .svg-wrap {{ width: 100%; overflow: auto; }}
    .svg-wrap svg {{ width: 100%; height: auto; display: block; }}
    .notes {{ margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px; color: var(--muted); font-size: 13px; }}
    .notes pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{safe_title}</h1>
    <div class="hint">由助手模式自动生成的静态流程图</div>
    <div class="panel">
      <div class="svg-wrap">
        {svg}
      </div>
      {notes_html}
    </div>
  </div>
</body>
</html>
"""

    async def execute(
        self,
        artifact_id: str,
        title: str,
        direction: str = "TB",
        layout_engine: str = "graphviz",
        mermaid: Optional[str] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            direction = direction if direction in {"TB", "BT", "LR", "RL"} else "TB"
            layout_engine = (layout_engine or "graphviz").lower()
            steps = steps or []
            edges = edges or []

            if layout_engine == "mermaid" or (layout_engine == "auto" and mermaid and not steps):
                mermaid_body = mermaid.strip() if mermaid else "flowchart TB\n  A[无步骤数据] --> B[请提供 steps 或 mermaid]"
                if not mermaid_body.startswith("flowchart "):
                    mermaid_body = f"flowchart {direction}\n{mermaid_body}"
                html_content = self._build_mermaid_html(title, mermaid_body, notes)
                render_engine = "mermaid"
            else:
                dot_source = self._build_dot_from_steps(steps, edges, direction, title)
                try:
                    svg = self._render_graphviz_svg(dot_source)
                    html_content = self._build_graphviz_html(title, svg, notes)
                    render_engine = "graphviz"
                except Exception as graphviz_exc:
                    if mermaid:
                        mermaid_body = mermaid.strip()
                    else:
                        mermaid_body = "flowchart TB\n  A[Graphviz 渲染失败] --> B[请检查输入数据]"
                    if not mermaid_body.startswith("flowchart "):
                        mermaid_body = f"flowchart {direction}\n{mermaid_body}"
                    html_content = self._build_mermaid_html(
                        title,
                        mermaid_body + f"\n%% Graphviz fallback: {html.escape(str(graphviz_exc))}",
                        notes,
                    )
                    render_engine = "mermaid"

            data = html_artifact_service.create_artifact(
                artifact_id,
                html_content,
                title=title,
                metadata={
                    "artifact_kind": "flowchart",
                    "direction": direction,
                    "layout_engine": render_engine,
                    "generated_at": datetime.now().isoformat(),
                    **(metadata or {}),
                },
            )
            data.pop("download_url", None)
            data.pop("share_endpoint", None)
            attach_document_artifact(
                data,
                data["file_path"],
                kind="html_artifact",
                format="html",
                title=title,
                preview_key="html_preview",
                generator=self.name,
                metadata={
                    "artifact_id": data.get("artifact_id"),
                    "artifact_kind": "flowchart",
                    "layout_engine": render_engine,
                },
            )
            return {
                "success": True,
                "data": data,
                "metadata": {
                    "generator": self.name,
                    "schema_version": "flowchart_html.v2",
                    "direction": direction,
                    "layout_engine": render_engine,
                    "artifact_id": data.get("artifact_id"),
                },
                "summary": f"流程图已生成：{data['artifact_id']}。右侧预览已可用。",
            }
        except Exception as exc:
            return {
                "success": False,
                "data": None,
                "metadata": {
                    "generator": self.name,
                    "schema_version": "flowchart_html.v2",
                },
                "summary": f"流程图生成失败: {exc}",
            }
