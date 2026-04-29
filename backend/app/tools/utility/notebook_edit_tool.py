"""
Notebook Edit Tool - Jupyter Notebook 编辑工具

参照 Claude Code 实现，支持对 Jupyter Notebook (.ipynb) 文件的单元格编辑操作。

功能：
- replace: 替换单元格内容
- insert: 插入新单元格
- delete: 删除单元格

安全机制：
- Read-Before-Edit：必须先读取文件才能编辑
- 文件修改时间检测：防止外部修改冲突
- JSON 格式验证

使用场景：
- 自动生成数据分析报告 Notebook
- 交互式污染溯源分析
- 批量更新分析文档
"""

import json
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class NotebookEditTool(LLMTool):
    """
    Jupyter Notebook 编辑工具

    支持 .ipynb 文件的单元格级别编辑操作，遵循 Read-Before-Edit 安全策略。
    """

    def __init__(self):
        function_schema = {
            "name": "notebook_edit",
            "description": (
                "编辑Jupyter Notebook单元格。支持replace/insert/delete；"
                "必须先read_file，单元格索引从0开始，insert需指定cell_type。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notebook_path": {
                        "type": "string",
                        "description": "ipynb文件路径"
                    },
                    "cell_id": {
                        "type": "string",
                        "description": "目标单元格ID或索引；insert可省略"
                    },
                    "new_source": {
                        "type": "string",
                        "description": "新的单元格内容"
                    },
                    "cell_type": {
                        "type": "string",
                        "enum": ["code", "markdown"],
                        "description": "单元格类型；insert必填"
                    },
                    "edit_mode": {
                        "type": "string",
                        "enum": ["replace", "insert", "delete"],
                        "description": "编辑模式：replace/insert/delete"
                    }
                },
                "required": ["notebook_path", "new_source"]
            }
        }

        super().__init__(
            name="notebook_edit",
            description="编辑 Jupyter Notebook (.ipynb) 文件的单元格",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        # 文件读取状态缓存（用于 Read-Before-Edit 验证）
        self._read_file_state: Dict[str, Dict[str, Any]] = {}

    async def execute(
        self,
        notebook_path: str = None,
        new_source: str = None,
        cell_id: str = None,
        cell_type: str = "code",
        edit_mode: str = "replace",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 Notebook 编辑操作

        Args:
            notebook_path: Notebook 文件路径
            new_source: 新的单元格内容
            cell_id: 目标单元格ID或索引
            cell_type: 单元格类型（code/markdown）
            edit_mode: 编辑模式（replace/insert/delete）

        Returns:
            {
                "success": true/false,
                "data": {...},
                "summary": "操作摘要"
            }
        """
        if not notebook_path:
            return {
                "success": False,
                "summary": "缺少 notebook_path 参数"
            }

        if new_source is None and edit_mode != "delete":
            return {
                "success": False,
                "summary": "缺少 new_source 参数"
            }

        # 标准化路径
        notebook_path = os.path.abspath(notebook_path)

        # 验证文件扩展名
        if not notebook_path.endswith('.ipynb'):
            return {
                "success": False,
                "summary": "文件必须是 Jupyter Notebook 格式（.ipynb 文件）"
            }

        # 验证参数
        if edit_mode not in ("replace", "insert", "delete"):
            return {
                "success": False,
                "summary": f"无效的 edit_mode: {edit_mode}，必须是 replace、insert 或 delete"
            }

        if edit_mode == "insert" and not cell_type:
            return {
                "success": False,
                "summary": "insert 模式必须指定 cell_type 参数（code 或 markdown）"
            }

        # Read-Before-Edit 验证
        if notebook_path not in self._read_file_state:
            return {
                "success": False,
                "summary": "文件尚未读取，请先用 read_file 工具读取此文件"
            }

        # 检查文件是否被外部修改
        read_state = self._read_file_state[notebook_path]
        current_mtime = os.path.getmtime(notebook_path)
        if current_mtime > read_state["timestamp"]:
            return {
                "success": False,
                "summary": "文件已被外部修改（文件时间戳变化），请重新读取后再编辑"
            }

        try:
            # 读取 notebook
            with open(notebook_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析 JSON
            try:
                notebook = json.loads(content)
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "summary": f"Notebook 文件不是有效的 JSON 格式: {str(e)}"
                }

            # 验证 notebook 结构
            if "cells" not in notebook:
                return {
                    "success": False,
                    "summary": "Notebook 格式无效：缺少 cells 字段"
                }

            cells = notebook["cells"]
            language = notebook.get("metadata", {}).get("language_info", {}).get("name", "python")

            # 解析 cell_id
            cell_index = self._parse_cell_id(cell_id, cells, edit_mode)

            if cell_index is None:
                return {
                    "success": False,
                    "summary": f"找不到单元格: {cell_id}"
                }

            # 执行编辑操作
            result = await self._edit_notebook(
                notebook, cells, cell_index, edit_mode, new_source, cell_type
            )

            if not result["success"]:
                return result

            # 保存文件
            updated_content = json.dumps(notebook, indent=1, ensure_ascii=False)

            with open(notebook_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)

            # 更新读取状态
            self._read_file_state[notebook_path] = {
                "content": updated_content,
                "timestamp": os.path.getmtime(notebook_path)
            }

            # 返回结果
            return {
                "success": True,
                "data": {
                    "cell_id": result.get("cell_id"),
                    "cell_type": result.get("cell_type", cell_type),
                    "language": language,
                    "edit_mode": edit_mode,
                    "new_source": new_source if edit_mode != "delete" else "",
                    "notebook_path": notebook_path,
                    "total_cells": len(cells)
                },
                "summary": self._format_summary(edit_mode, result, cell_index, len(cells))
            }

        except FileNotFoundError:
            return {
                "success": False,
                "summary": f"Notebook 文件不存在: {notebook_path}"
            }
        except Exception as e:
            logger.error("notebook_edit_failed", path=notebook_path, error=str(e), exc_info=True)
            return {
                "success": False,
                "summary": f"编辑 Notebook 失败: {str(e)}"
            }

    def _parse_cell_id(
        self,
        cell_id: Optional[str],
        cells: List[Dict],
        edit_mode: str
    ) -> Optional[int]:
        """
        解析 cell_id 为单元格索引

        支持两种格式：
        1. 真实 ID：直接匹配 cells[i].id
        2. 索引格式：cell-0, cell-1, ...

        Returns:
            单元格索引，未找到返回 None
        """
        # 如果没有指定 cell_id，默认处理
        if cell_id is None:
            if edit_mode == "insert":
                return 0  # 在开头插入
            return None

        # 尝试作为索引格式解析（cell-0, cell-1, ...）
        if cell_id.startswith("cell-"):
            try:
                index = int(cell_id.split("-")[1])
                if 0 <= index < len(cells):
                    return index
            except (ValueError, IndexError):
                pass

        # 尝试通过真实 ID 查找
        for i, cell in enumerate(cells):
            if cell.get("id") == cell_id:
                return i

        # 未找到
        return None

    async def _edit_notebook(
        self,
        notebook: Dict,
        cells: List[Dict],
        cell_index: int,
        edit_mode: str,
        new_source: Optional[str],
        cell_type: str
    ) -> Dict[str, Any]:
        """
        执行实际的编辑操作

        Returns:
            {"success": true/false, "cell_id": "...", "cell_type": "..."}
        """
        try:
            # 自动替换localhost URL为外网URL
            if new_source:
                new_source = self._replace_localhost_urls(new_source)
            # 检查 notebook 版本（确定是否需要生成 cell_id）
            nbformat = notebook.get("nbformat", 4)
            nbformat_minor = notebook.get("nbformat_minor", 0)
            use_cell_id = nbformat > 4 or (nbformat == 4 and nbformat_minor >= 5)

            if edit_mode == "delete":
                # 删除单元格
                deleted_cell = cells.pop(cell_index)
                return {
                    "success": True,
                    "cell_id": deleted_cell.get("id"),
                    "cell_type": deleted_cell.get("cell_type")
                }

            elif edit_mode == "insert":
                # 插入新单元格
                new_cell = {
                    "cell_type": cell_type,
                    "id": str(uuid.uuid4())[:12] if use_cell_id else None,
                    "source": new_source or "",
                    "metadata": {}
                }

                if cell_type == "code":
                    new_cell["execution_count"] = None
                    new_cell["outputs"] = []

                # 在指定位置后插入（cell_index + 1）
                cells.insert(cell_index + 1, new_cell)

                return {
                    "success": True,
                    "cell_id": new_cell.get("id"),
                    "cell_type": cell_type
                }

            else:  # replace
                # 替换单元格内容
                target_cell = cells[cell_index]

                # 更新源代码
                target_cell["source"] = new_source

                # 如果是代码单元格，清空执行状态
                if target_cell.get("cell_type") == "code":
                    target_cell["execution_count"] = None
                    target_cell["outputs"] = []

                # 更新单元格类型（如果指定）
                if cell_type and cell_type != target_cell.get("cell_type"):
                    target_cell["cell_type"] = cell_type
                    if cell_type == "code":
                        target_cell["execution_count"] = None
                        target_cell["outputs"] = []

                return {
                    "success": True,
                    "cell_id": target_cell.get("id"),
                    "cell_type": target_cell.get("cell_type")
                }

        except IndexError:
            return {
                "success": False,
                "error": f"单元格索引 {cell_index} 超出范围（共 {len(cells)} 个单元格）"
            }
        except Exception as e:
            logger.error("edit_operation_failed", mode=edit_mode, error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    def _format_summary(
        self,
        edit_mode: str,
        result: Dict,
        cell_index: int,
        total_cells: int
    ) -> str:
        """格式化操作摘要"""
        cell_type = result.get("cell_type", "code")

        if edit_mode == "delete":
            return f"已删除 cell-{cell_index}（{cell_type}）"
        elif edit_mode == "insert":
            return f"已在 cell-{cell_index} 后插入新单元格（{cell_type}），当前共 {total_cells} 个单元格"
        else:  # replace
            return f"已更新 cell-{cell_index} 的内容（{cell_type}）"

    def mark_file_as_read(self, file_path: str, content: str):
        """
        标记文件为已读取（Read-Before-Edit 机制）

        此方法应由 read_file_tool 在读取 .ipynb 文件后调用
        """
        file_path = os.path.abspath(file_path)
        self._read_file_state[file_path] = {
            "content": content,
            "timestamp": os.path.getmtime(file_path)
        }

    def _replace_localhost_urls(self, text: str) -> str:
        """
        替换localhost URL为外网URL

        Args:
            text: 包含localhost URL的文本

        Returns:
            替换后的文本
        """
        try:
            from config.settings import settings
            frontend_base_url = settings.frontend_base_url

            # 替换各种可能的localhost格式
            text = text.replace('http://localhost:5174', frontend_base_url)
            text = text.replace('http://127.0.0.1:5174', frontend_base_url)
            text = text.replace('http://localhost:5173', frontend_base_url)
            text = text.replace('http://127.0.0.1:5173', frontend_base_url)

            logger.info(
                "localhost_urls_replaced",
                frontend_base_url=frontend_base_url,
                replacements_count=text.count(frontend_base_url)
            )

            return text
        except Exception as e:
            logger.warning("url_replace_failed", error=str(e))
            return text


# 全局实例（供 read_file_tool 调用）
_notebook_edit_instance: Optional[NotebookEditTool] = None


def get_notebook_edit_tool() -> NotebookEditTool:
    """获取 NotebookEditTool 单例"""
    global _notebook_edit_instance
    if _notebook_edit_instance is None:
        _notebook_edit_instance = NotebookEditTool()
    return _notebook_edit_instance


def mark_notebook_as_read(file_path: str, content: str):
    """
    标记 notebook 文件为已读取

    此函数供 read_file_tool 在读取 .ipynb 文件后调用，
    用于建立 Read-Before-Edit 安全机制。
    """
    tool = get_notebook_edit_tool()
    tool.mark_file_as_read(file_path, content)
