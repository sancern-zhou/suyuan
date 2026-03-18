"""
validate_tool 工具

验证工具定义：语法检查、导入测试、schema验证
"""

from app.tools.base import LLMTool, ToolCategory
from typing import Dict, Any, Optional
import structlog
import os
import subprocess
import sys

logger = structlog.get_logger()


class ValidateToolTool(LLMTool):
    """验证工具定义"""

    def __init__(self):
        super().__init__(
            name="validate_tool",
            description="验证工具定义（语法检查、导入测试、schema验证）",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        验证工具定义

        Args:
            tool_path: 工具文件路径（如 backend/app/tools/analysis/my_tool/tool.py）
            check_syntax: 是否检查语法（默认 True）
            check_import: 是否测试导入（默认 True）
            check_schema: 是否验证 schema（默认 True）

        Returns:
            验证结果
        """
        tool_path = kwargs.get("tool_path")
        if not tool_path:
            return {
                "success": False,
                "data": {},
                "summary": "错误：缺少 tool_path 参数"
            }

        check_syntax = kwargs.get("check_syntax", True)
        check_import = kwargs.get("check_import", True)
        check_schema = kwargs.get("check_schema", True)

        # 规范化路径
        if not os.path.isabs(tool_path):
            # 如果是相对路径，添加项目根目录前缀
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            tool_path = os.path.join(project_root, tool_path)

        results = {
            "tool_path": tool_path,
            "checks": {}
        }

        # 1. 语法检查
        if check_syntax:
            syntax_result = await self._check_syntax(tool_path)
            results["checks"]["syntax"] = syntax_result

        # 2. 导入测试
        if check_import:
            import_result = await self._check_import(tool_path)
            results["checks"]["import"] = import_result

        # 3. Schema验证
        if check_schema:
            schema_result = await self._check_schema(tool_path)
            results["checks"]["schema"] = schema_result

        # 汇总结果
        all_passed = all(
            check.get("passed", False)
            for check in results["checks"].values()
        )

        return {
            "success": True,
            "data": results,
            "summary": f"验证完成：{'全部通过' if all_passed else '存在失败项'}"
        }

    async def _check_syntax(self, tool_path: str) -> Dict[str, Any]:
        """检查Python语法"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", tool_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return {
                    "passed": True,
                    "message": "语法检查通过"
                }
            else:
                return {
                    "passed": False,
                    "message": "语法错误",
                    "error": result.stderr
                }
        except Exception as e:
            return {
                "passed": False,
                "message": "语法检查失败",
                "error": str(e)
            }

    async def _check_import(self, tool_path: str) -> Dict[str, Any]:
        """测试导入"""
        try:
            # 提取模块路径
            # backend/app/tools/analysis/my_tool/tool.py -> app.tools.analysis.my_tool
            rel_path = tool_path.replace("backend/", "").replace(".py", "").replace(os.sep, ".")
            module_path = rel_path

            # 尝试导入
            import importlib
            importlib.import_module(module_path)

            return {
                "passed": True,
                "message": f"导入成功：{module_path}"
            }
        except ImportError as e:
            return {
                "passed": False,
                "message": "导入失败",
                "error": f"ImportError: {str(e)}"
            }
        except Exception as e:
            return {
                "passed": False,
                "message": "导入测试失败",
                "error": str(e)
            }

    async def _check_schema(self, tool_path: str) -> Dict[str, Any]:
        """验证工具Schema"""
        try:
            # 读取文件内容
            with open(tool_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 检查是否继承自 LLMTool
            has_llm_tool = "LLMTool" in content and "class " in content

            # 检查是否有 execute 方法
            has_execute = "def execute(" in content or "async def execute(" in content

            # 检查是否有 ToolMetadata
            has_metadata = "ToolMetadata" in content

            # 检查是否有 __init__ 方法
            has_init = "def __init__(" in content

            issues = []
            if not has_llm_tool:
                issues.append("未找到 LLMTool 基类")
            if not has_execute:
                issues.append("未找到 execute 方法")
            if not has_metadata:
                issues.append("未找到 ToolMetadata")
            if not has_init:
                issues.append("未找到 __init__ 方法")

            if issues:
                return {
                    "passed": False,
                    "message": "Schema验证失败",
                    "issues": issues
                }
            else:
                return {
                    "passed": True,
                    "message": "Schema验证通过"
                }
        except Exception as e:
            return {
                "passed": False,
                "message": "Schema验证失败",
                "error": str(e)
            }
