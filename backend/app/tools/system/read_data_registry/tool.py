"""
read_data_registry 工具 - 读取数据注册表中的文件

允许 LLM 按需读取已保存的数据文件（metadata.json, data.json, quality_report.json）
"""

from app.agent.tools.base import BaseTool, ToolConfig
from app.agent.context.execution_context import ExecutionContext
import json
from pathlib import Path
from typing import Dict, Any, Optional
import subprocess


class ReadDataRegistryTool(BaseTool):
    """读取数据注册表中的文件"""

    @property
    def config(self) -> ToolConfig:
        return ToolConfig(
            name="read_data_registry",
            description="""读取 backend_data_registry 中保存的数据文件。

使用场景：
- 查看工具返回的完整数据
- 检查数据的元信息（记录数、时间范围等）
- 读取质量报告

示例：
- read_data_registry(data_id="weather_001", file_type="metadata")  # 查看元信息
- read_data_registry(data_id="weather_001", file_type="data", jq_filter=".[:5]")  # 查看前5条数据
""",
            parameters={
                "type": "object",
                "properties": {
                    "data_id": {
                        "type": "string",
                        "description": "数据ID（如 weather_001, vocs_unified:xxx）"
                    },
                    "file_type": {
                        "type": "string",
                        "enum": ["metadata", "data", "quality_report"],
                        "description": "文件类型：metadata=元信息, data=完整数据, quality_report=质量报告"
                    },
                    "jq_filter": {
                        "type": "string",
                        "description": "可选的 jq 过滤表达式（如 '.[:10]' 查看前10条，'.[].temperature' 提取温度字段）"
                    },
                    "max_items": {
                        "type": "integer",
                        "description": "最多返回的记录数（默认100，避免返回过大数据）",
                        "default": 100
                    }
                },
                "required": ["data_id", "file_type"]
            },
            requires_context=True
        )

    async def execute(
        self,
        context: ExecutionContext,
        data_id: str,
        file_type: str,
        jq_filter: Optional[str] = None,
        max_items: int = 100
    ) -> Dict[str, Any]:
        """执行数据读取"""

        # 1. 构造文件路径
        base_path = Path("backend_data_registry") / data_id

        if not base_path.exists():
            return {
                "status": "error",
                "error": f"数据ID不存在: {data_id}",
                "suggestion": "请检查 data_id 是否正确，或使用 bash 工具查看可用的数据ID"
            }

        file_map = {
            "metadata": base_path / "metadata.json",
            "data": base_path / "data.json",
            "quality_report": base_path / "quality_report.json"
        }

        file_path = file_map.get(file_type)
        if not file_path or not file_path.exists():
            available_files = [f.name for f in base_path.glob("*.json")]
            return {
                "status": "error",
                "error": f"文件不存在: {file_type}",
                "available_files": available_files
            }

        # 2. 读取文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"JSON 解析失败: {str(e)}"
            }

        # 3. 应用 jq 过滤（如果提供）
        if jq_filter:
            try:
                result = subprocess.run(
                    ["jq", jq_filter],
                    input=json.dumps(data, ensure_ascii=False),
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                if result.returncode == 0:
                    filtered_data = json.loads(result.stdout)
                    data = filtered_data
                else:
                    return {
                        "status": "error",
                        "error": f"jq 过滤失败: {result.stderr}"
                    }
            except FileNotFoundError:
                # jq 未安装，跳过过滤
                pass
            except Exception as e:
                return {
                    "status": "error",
                    "error": f"jq 执行失败: {str(e)}"
                }

        # 4. 限制返回数据量
        result_data = data
        truncated = False

        if file_type == "data" and isinstance(data, list):
            if len(data) > max_items:
                result_data = data[:max_items]
                truncated = True

        # 5. 构造返回结果
        return {
            "status": "success",
            "file_path": str(file_path),
            "file_type": file_type,
            "data": result_data,
            "metadata": {
                "total_records": len(data) if isinstance(data, list) else None,
                "returned_records": len(result_data) if isinstance(result_data, list) else None,
                "truncated": truncated
            },
            "summary": self._generate_summary(file_type, result_data, truncated, len(data) if isinstance(data, list) else 0)
        }

    def _generate_summary(self, file_type: str, data: Any, truncated: bool, total: int) -> str:
        """生成数据摘要"""
        if file_type == "metadata":
            return f"元信息: {json.dumps(data, ensure_ascii=False, indent=2)}"
        elif file_type == "data":
            records_info = f"共 {total} 条记录" + (f"，仅显示前 {len(data)} 条" if truncated else "")
            return f"数据内容: {records_info}"
        elif file_type == "quality_report":
            return f"质量报告: {json.dumps(data, ensure_ascii=False, indent=2)}"
        return ""


# 工具注册
tool = ReadDataRegistryTool()
