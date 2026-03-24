"""
read_data_registry 工具 - 读取数据注册表中的数据

允许 LLM 按需读取已保存的数据（支持时间范围过滤和字段选择）
"""

from app.tools.base.tool_interface import LLMTool, ToolCategory
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import subprocess
import structlog

logger = structlog.get_logger()


class ReadDataRegistryTool(LLMTool):
    """读取数据注册表中的文件"""

    # 常见时间字段名（用于自动识别）
    TIME_FIELDS = [
        'timestamp', 'time', 'datetime', 'date',
        'observation_time', 'data_time', 'record_time',
        '时间', '观测时间', '数据时间'
    ]

    def __init__(self):
        super().__init__(
            name="read_data_registry",
            description="""从 backend_data_registry/datasets/ 读取已保存的数据。

使用场景：
- 查看工具返回的完整数据
- 按时间范围过滤数据
- 选择特定字段
- 对数据进行高级过滤

【字段使用说明】
方式1 - 先查看字段（推荐）：
- read_data_registry(data_id="xxx", list_fields=true)  # 查看可用字段

方式2 - 直接使用字段（容错）：
- read_data_registry(data_id="xxx", fields=["temperature", "humidity"])
- 如果字段名不匹配，工具会返回完整的可用字段列表，您可以根据返回信息重试

时间过滤示例：
- read_data_registry(data_id="weather_001", time_range="2024-01-01,2024-01-31")  # 指定月份
- read_data_registry(data_id="weather_001", time_range="2024-01-01,")  # 从某日期开始
- read_data_registry(data_id="weather_001", time_range=",2024-01-31")  # 到某日期结束

组合使用：
- read_data_registry(data_id="weather_001", time_range="2024-01-01,2024-01-31", fields=["temperature", "humidity"])

注意：
- time_range 格式：开始日期,结束日期（逗号分隔，任一可省略）
- 时间字段会自动识别（timestamp, time, datetime, date 等）
- 如果 fields 参数中的字段名不存在，工具会返回字段不匹配错误及可用字段列表
""",
            category=ToolCategory.QUERY,
            version="2.1.0",
            requires_context=True
        )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "data_id": {
                        "type": "string",
                        "description": "数据ID（如 weather_001, vocs_unified:xxx）"
                    },
                    "list_fields": {
                        "type": "boolean",
                        "description": "【推荐】设置为 true 时，只返回可用字段列表（不返回数据），用于确认正确的字段名后再使用 fields 参数"
                    },
                    "time_range": {
                        "type": "string",
                        "description": "时间范围过滤，格式：开始日期,结束日期（如 '2024-01-01,2024-01-31'）。任一可省略（'2024-01-01,' 从某日期开始；',2024-01-31' 到某日期结束）。支持格式：YYYY-MM-DD, YYYY-MM-DD HH:MM:SS"
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "选择特定字段（如 ['temperature', 'humidity']）。⚠️ 务必先用 list_fields=true 确认字段名，避免因字段名错误导致查询结果为空"
                    },
                    "jq_filter": {
                        "type": "string",
                        "description": "高级：jq 过滤表达式。注意：数据是数组格式，需要用 .[] 迭代或用 map/select。示例：'.[] | select(.temperature > 30)' 或 'map(select(.measurements.PM10 == null))'。注意：jq_filter 在 time_range 和 fields 之后应用"
                    }
                },
                "required": ["data_id"]
            }
        }

    async def execute(
        self,
        context=None,
        data_id: str = None,
        list_fields: bool = False,
        time_range: Optional[str] = None,
        fields: Optional[List[str]] = None,
        jq_filter: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行数据读取

        从 backend_data_registry/datasets/ 读取 DataRegistry 格式的数据。
        """

        # 从 DataRegistry 加载数据
        data_registry_path = Path("backend_data_registry/datasets") / f"{data_id.replace(':', '_')}.json"

        if not data_registry_path.exists():
            return {
                "success": False,
                "error": f"数据ID不存在: {data_id}",
                "suggestion": "请检查 data_id 是否正确",
                "searched_path": f"backend_data_registry/datasets/{data_id.replace(':', '_')}.json"
            }

        return await self._load_from_data_registry(
            data_registry_path, data_id, list_fields, time_range, fields, jq_filter
        )

    async def _load_from_data_registry(
        self, file_path: Path, data_id: str,
        list_fields: bool, time_range: Optional[str], fields: Optional[List[str]], jq_filter: Optional[str]
    ) -> Dict[str, Any]:
        """从 DataRegistry 格式加载数据"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON 解析失败: {str(e)}"}

        # DataRegistry 直接存储数据数组
        if not isinstance(data, list):
            return {"success": False, "error": f"数据格式错误: 期望数组，得到 {type(data).__name__}"}

        # 【新增】list_fields 功能：只返回字段列表
        if list_fields:
            if data:
                first_record = data[0]
                if isinstance(first_record, dict):
                    # 获取所有字段名（包括嵌套字段）
                    field_list = self._extract_all_fields(first_record)
                    return {
                        "success": True,
                        "data": {
                            "data_id": data_id,
                            "total_fields": len(field_list),
                            "fields": field_list,
                            "sample_values": self._get_sample_values(first_record, field_list[:10])
                        },
                        "summary": f"数据ID {data_id} 包含 {len(field_list)} 个字段：{', '.join(field_list[:15])}{'...' if len(field_list) > 15 else ''}"
                    }
            return {"success": False, "error": "数据为空，无法提取字段"}

        # 应用过滤
        filter_info = {}
        data, filter_info = self._apply_filters(data, time_range, fields)

        # 【容错处理】检测字段不匹配，返回可用字段信息
        if fields and filter_info.get("field_match_info", {}).get("matched") is False:
            field_info = filter_info["field_match_info"]
            available_fields = field_info.get("available_fields", [])
            mismatched_fields = field_info.get("mismatched_fields", [])

            # 将字段不匹配信息放在 data 字段中，避免被格式转换丢失
            return {
                "status": "failed",
                "success": False,
                "data": {
                    "error_type": "field_mismatch",
                    "requested_fields": fields,
                    "mismatched_fields": mismatched_fields,
                    "available_fields": available_fields,
                    "total_available": len(available_fields),
                    "suggestion": f"您请求的字段 {mismatched_fields} 不存在。请从以下可用字段中选择：{', '.join(available_fields[:20])}{'...' if len(available_fields) > 20 else ''}",
                    "correct_usage": f'read_data_registry(data_id="{data_id}", fields={["字段1", "字段2"]})'
                },
                "metadata": {
                    "tool_name": "read_data_registry",
                    "error": "字段名称不匹配"
                },
                "summary": f"字段名称不匹配。请求的字段 {mismatched_fields} 不存在，共有 {len(available_fields)} 个可用字段。请查看 data 字段获取完整字段列表。"
            }

        # 应用 jq 过滤（带智能修正）
        if jq_filter:
            try:
                # 智能修正：如果用户直接写 .field 而不是 .[] | .field
                # 自动添加 .[] 迭代器
                corrected_filter = self._auto_correct_jq_filter(jq_filter)
                if corrected_filter != jq_filter:
                    filter_info["jq_filter_corrected"] = {
                        "original": jq_filter,
                        "corrected": corrected_filter
                    }
                    jq_filter = corrected_filter

                result = subprocess.run(
                    ["jq", jq_filter],
                    input=json.dumps(data, ensure_ascii=False),
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    filter_info["jq_filter"] = jq_filter
                else:
                    # 提供更友好的错误提示
                    error_hint = self._get_jq_error_hint(result.stderr, jq_filter)
                    return {
                        "success": False,
                        "error": f"jq 过滤失败: {result.stderr}",
                        "hint": error_hint,
                        "suggestion": "数据是数组格式，请使用 .[] 迭代或 map/select 函数"
                    }
            except FileNotFoundError:
                filter_info["jq_warning"] = "jq 未安装，跳过 jq 过滤"
            except Exception as e:
                return {"success": False, "error": f"jq 执行失败: {str(e)}"}

        return {
            "success": True,
            "file_path": str(file_path),
            "data": data,
            "metadata": {
                "total_records": filter_info.get("original_count", len(data)),
                "returned_records": len(data),
                "filter_applied": bool(filter_info),
                "filter_details": filter_info,
                "source": "data_registry",
                "generator": "read_data_registry",
                "tool_name": "read_data_registry"
            },
            "summary": self._generate_summary(data, filter_info)
        }

    def _apply_filters(
        self,
        data: List[Dict],
        time_range: Optional[str],
        fields: Optional[List[str]]
    ) -> tuple[List[Dict], Dict[str, Any]]:
        """应用时间范围和字段过滤"""
        filter_info = {}
        original_count = len(data)
        result = data

        # 1. 时间范围过滤
        if time_range:
            result, time_info = self._filter_by_time_range(result, time_range)
            if time_info:
                filter_info.update(time_info)

        # 2. 字段选择
        if fields:
            result, field_info = self._select_fields(result, fields)
            filter_info["fields_selected"] = fields
            filter_info["field_match_info"] = field_info

        filter_info["original_count"] = original_count
        filter_info["filtered_count"] = len(result)

        return result, filter_info

    def _filter_by_time_range(self, data: List[Dict], time_range: str) -> tuple[List[Dict], Dict[str, Any]]:
        """按时间范围过滤数据"""
        try:
            # 解析时间范围
            parts = time_range.split(',')
            start_str = parts[0].strip() if parts[0] else None
            end_str = parts[1].strip() if len(parts) > 1 and parts[1] else None

            if not start_str and not end_str:
                return data, {}

            # 尝试解析时间
            start_dt = self._parse_datetime(start_str) if start_str else None
            end_dt = self._parse_datetime(end_str) if end_str else None

            # 查找时间字段
            time_field = self._find_time_field(data)
            if not time_field:
                return data, {
                    "time_filter_warning": f"未找到时间字段，尝试的字段: {self.TIME_FIELDS}",
                    "time_range_requested": time_range
                }

            # 过滤数据
            filtered_data = []
            for record in data:
                record_time = self._extract_record_time(record, time_field)
                if record_time is None:
                    continue

                if start_dt and record_time < start_dt:
                    continue
                if end_dt and record_time > end_dt:
                    continue

                filtered_data.append(record)

            return filtered_data, {
                "time_field_used": time_field,
                "time_range_applied": f"{start_str or ''},{end_str or ''}",
                "time_filter_count": len(filtered_data)
            }

        except Exception as e:
            return data, {
                "time_filter_error": str(e),
                "time_range_requested": time_range
            }

    def _find_time_field(self, data: List[Dict]) -> Optional[str]:
        """查找数据中的时间字段"""
        if not data:
            return None

        first_record = data[0]

        # 按优先级查找
        for field in self.TIME_FIELDS:
            if field in first_record:
                return field

        # 尝试自动识别（字段名包含 time/date 关键词）
        for key in first_record.keys():
            key_lower = key.lower()
            if any(keyword in key_lower for keyword in ['time', 'date', 'timestamp']):
                return key

        return None

    def _extract_record_time(self, record: Dict, time_field: str) -> Optional[datetime]:
        """从记录中提取时间"""
        time_value = record.get(time_field)
        if time_value is None:
            return None

        # 尝试解析各种时间格式
        return self._parse_datetime(time_value)

    def _parse_datetime(self, time_str: str) -> Optional[datetime]:
        """解析时间字符串"""
        if not time_str:
            return None

        # 常见时间格式
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d',
            '%Y年%m月%d日',
            '%Y%m%d',
            '%Y%m%d%H%M%S'
        ]

        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except (ValueError, TypeError):
                continue

        # 尝试 ISO 格式
        try:
            return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

        return None

    def _select_fields(self, data: List[Dict], fields: List[str]) -> tuple[List[Dict], Dict[str, Any]]:
        """选择指定字段，并检测字段匹配情况

        返回: (filtered_data, field_match_info)
        - field_match_info: 包含字段匹配状态、可用字段等信息
        """
        if not data:
            return [], {"matched": True, "available_fields": []}

        first_record = data[0] if isinstance(data[0], dict) else {}

        # 获取所有可用字段（包括嵌套字段）
        available_fields = self._extract_all_fields(first_record)

        # 请求的字段可能包含点号路径（如 "old_standard.exceed_details"）
        # 需要检查这些路径是否存在
        matched_fields = []
        mismatched_fields = []

        for requested_field in fields:
            if self._field_exists(first_record, requested_field):
                matched_fields.append(requested_field)
            else:
                mismatched_fields.append(requested_field)

        field_info = {
            "matched": len(mismatched_fields) == 0,
            "requested_count": len(fields),
            "matched_count": len(matched_fields),
            "mismatched_count": len(mismatched_fields),
            "available_fields": sorted(available_fields),
        }

        if mismatched_fields:
            field_info["mismatched_fields"] = sorted(mismatched_fields)
            field_info["matched_fields"] = sorted(matched_fields)

        # 执行字段过滤（支持嵌套路径）
        result = []
        for record in data:
            if isinstance(record, dict):
                filtered_record = self._select_fields_from_record(record, fields)
                result.append(filtered_record)
            else:
                result.append(record)

        return result, field_info

    def _field_exists(self, record: Dict, field_path: str) -> bool:
        """检查字段路径是否存在（支持嵌套路径如 "old_standard.exceed_details"）"""
        parts = field_path.split(".")
        current = record
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False
        return True

    def _select_fields_from_record(self, record: Dict, fields: List[str]) -> Dict:
        """从记录中选择指定的字段（支持嵌套路径）"""
        result = {}
        for field_path in fields:
            parts = field_path.split(".")
            current = record
            try:
                for part in parts:
                    current = current[part]
                # 构建嵌套结果
                self._set_nested_value(result, parts, current)
            except (KeyError, TypeError):
                # 字段不存在，跳过
                pass
        return result

    def _set_nested_value(self, target: Dict, path_parts: List[str], value: Any) -> None:
        """设置嵌套字典的值"""
        current = target
        for key in path_parts[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path_parts[-1]] = value

    def _extract_all_fields(self, record: Dict, prefix: str = "") -> List[str]:
        """递归提取所有字段名（包括嵌套字段）"""
        fields = []
        for key, value in record.items():
            full_key = f"{prefix}.{key}" if prefix else key
            fields.append(full_key)
            if isinstance(value, dict):
                fields.extend(self._extract_all_fields(value, full_key))
        return fields

    def _get_sample_values(self, record: Dict, fields: List[str]) -> Dict[str, Any]:
        """获取指定字段的示例值"""
        sample_values = {}
        for field in fields:
            value = record
            for key in field.split("."):
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = None
                    break
            if value is not None:
                # 限制值的长度
                if isinstance(value, str):
                    sample_values[field] = value[:50] + "..." if len(value) > 50 else value
                elif isinstance(value, (list, dict)):
                    sample_values[field] = f"<{type(value).__name__} length={len(value)}>"
                else:
                    sample_values[field] = value
        return sample_values

    def _generate_summary(self, data: Any, filter_info: Dict) -> str:
        """生成数据摘要"""
        if isinstance(data, list):
            total = filter_info.get("original_count", len(data))
            returned = len(data)
            if filter_info.get("filter_applied"):
                filters_applied = []
                if "time_field_used" in filter_info:
                    filters_applied.append(f"时间范围: {filter_info['time_range_applied']}")
                if "fields_selected" in filter_info:
                    filters_applied.append(f"字段: {filter_info['fields_selected']}")
                if "jq_filter" in filter_info:
                    filters_applied.append(f"jq: {filter_info['jq_filter']}")

                filter_str = "; ".join(filters_applied)
                return f"数据内容: 原始 {total} 条 -> 过滤后 {returned} 条（{filter_str}）"
            else:
                return f"数据内容: 共 {returned} 条记录"
        else:
            return f"数据内容: {json.dumps(data, ensure_ascii=False)[:200]}"

    def _auto_correct_jq_filter(self, jq_filter: str) -> str:
        """智能修正 jq 过滤表达式

        常见错误模式：
        1. 直接写 .field (应该是 .[] | .field 或 map(.field))
        2. .field == value (应该是 .[] | select(.field == value))
        """
        jq_filter = jq_filter.strip()

        # 如果已经包含 .[] 或 map(，说明用户已经知道需要迭代
        if ".[]" in jq_filter or "map(" in jq_filter or "select(" in jq_filter:
            return jq_filter

        # 模式1：简单的字段比较，如 .field == null 或 .field == ""
        if jq_filter.startswith(".") and "==" in jq_filter:
            # 将 .field == null 转换为 map(select(.field == null))
            return f"map(select({jq_filter}))"

        # 模式2：简单的字段访问，如 .field
        if jq_filter.startswith(".") and "==" not in jq_filter and "|" not in jq_filter:
            # 将 .field 转换为 map(.field)
            return f"map({jq_filter})"

        return jq_filter

    def _get_jq_error_hint(self, stderr: str, jq_filter: str) -> str:
        """根据 jq 错误信息提供友好提示"""
        if "Cannot index array" in stderr:
            return "数据是数组格式，需要使用 .[] 迭代或使用 map/select 函数"
        elif "syntax error" in stderr:
            return "jq 语法错误，请检查表达式格式"
        elif "unexpected end" in stderr:
            return "jq 表达式未结束，可能缺少括号或引号"
        else:
            return "请检查 jq 表达式语法"


# 工具注册
tool = ReadDataRegistryTool()
