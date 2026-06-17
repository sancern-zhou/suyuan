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
from app.services.data_registry import data_registry
from app.tools.resource_refs import build_data_ref, build_file_ref, merge_refs
from app.utils.path_config import get_datasets_dir
from app.tools.system.data_registry_read_state import get_data_registry_read_state

logger = structlog.get_logger()


class ReadDataRegistryTool(LLMTool):
    """读取数据注册表中的文件"""

    DEFAULT_MAX_RECORDS = 200

    # 常见时间字段名（用于自动识别）
    TIME_FIELDS = [
        'timestamp', 'time', 'datetime', 'date',
        'observation_time', 'data_time', 'record_time',
        '时间', '观测时间', '数据时间'
    ]

    def __init__(self):
        super().__init__(
            name="read_data_registry",
            description=(
                "读取DataRegistry中已保存的数据。"
                "支持数组型明细数据的时间范围过滤、结构化where筛选、select取列/别名和jq聚合过滤；"
                "支持对象型报表数据包的视图列表和按view读取。读取 report_data_id 且不指定 view 时，"
                "默认返回 reporting 报告口径视图；只有确需原始接口字段时才显式读取 raw/result。"
                f"明细数组最多返回{self.DEFAULT_MAX_RECORDS}条。"
            ),
            category=ToolCategory.QUERY,
            version="2.2.0",
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
                        "description": "数组型数据返回字段列表和时间范围；对象型报表包返回包结构和视图列表"
                    },
                    "list_views": {
                        "type": "boolean",
                        "description": "对象型报表包专用：只返回可用视图列表和每个视图的字段；需要了解结构时使用"
                    },
                    "view": {
                        "type": "string",
                        "description": "对象型报表包专用：读取指定视图，如 reporting、cities、regions、province、stations、aggregate、raw、result。不传时默认 reporting；raw/result 是原始接口字段"
                    },
                    "time_range": {
                        "type": "string",
                        "description": (
                            "读取数据必填，格式'开始,结束'；任一端可省略，支持日期或日期时间。"
                            f"过滤后明细超过{self.DEFAULT_MAX_RECORDS}条时不会直接返回完整data。"
                        )
                    },
                    "where": {
                        "description": (
                            "结构化行筛选，优先用于简单筛选，避免写jq。"
                            "支持对象等值筛选，如 {\"cityName\":\"珠三角\"}；"
                            "也支持条件数组，如 [{\"field\":\"cityName\",\"op\":\"=\",\"value\":\"珠三角\"}]。"
                            "op支持 =、!=、in、not_in、contains、>、>=、<、<=。"
                        ),
                        "oneOf": [
                            {"type": "object"},
                            {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "field": {"type": "string"},
                                        "op": {"type": "string"},
                                        "value": {}
                                    },
                                    "required": ["field", "value"]
                                }
                            }
                        ]
                    },
                    "select": {
                        "description": (
                            "结构化取列和别名映射，优先用于简单取字段，避免写jq对象。"
                            "对象格式为 {\"输出列名\":\"源字段名\"}，如 {\"年份\":\"timePoint\",\"臭氧\":\"o3_8h\"}；"
                            "数组格式等价于 fields，如 [\"timePoint\", \"o3_8h\"]。"
                        ),
                        "oneOf": [
                            {"type": "object", "additionalProperties": {"type": "string"}},
                            {"type": "array", "items": {"type": "string"}}
                        ]
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"限制返回明细条数，默认不额外截断；明细数组仍受{self.DEFAULT_MAX_RECORDS}条上限保护"
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "选择特定字段；简单取列优先使用 select。建议先用 list_fields 或 list_views 确认字段名"
                    },
                    "jq_filter": {
                        "type": "string",
                        "description": "高级jq过滤表达式。简单筛选/取列优先使用 where/select；只有结构化参数无法表达时才使用 jq_filter"
                    }
                },
                "anyOf": [
                    {"required": ["data_id"]},                # 报表包默认读取 reporting；数组型数据仍建议带 time_range
                    {"required": ["data_id", "list_fields"]},  # list_fields 模式（不需要 time_range）
                    {"required": ["data_id", "list_views"]},   # 对象型报表包视图列表
                    {"required": ["data_id", "view"]},         # 对象型报表包指定视图
                    {"required": ["data_id", "time_range"]}    # 数组型数据读取模式
                ]
            }
        }

    async def execute(
        self,
        context=None,
        data_id: str = None,
        list_fields: bool = False,
        list_views: bool = False,
        view: Optional[str] = None,
        time_range: Optional[str] = None,
        fields: Optional[List[str]] = None,
        where: Optional[Any] = None,
        select: Optional[Any] = None,
        limit: Optional[int] = None,
        jq_filter: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行数据读取

        从 backend_data_registry/datasets/ 读取 DataRegistry 格式的数据。
        """

        # 从 DataRegistry 加载数据。优先使用 registry 元数据，兼容旧的路径推断。
        data_registry_path = self._resolve_registry_path(data_id)

        if not data_registry_path.exists():
            return {
                "success": False,
                "error": f"数据ID不存在: {data_id}",
                "suggestion": "请检查 data_id 是否正确",
                "searched_path": f"backend_data_registry/datasets/{data_id.replace(':', '_')}.json"
            }

        result = await self._load_from_data_registry(
            data_registry_path, data_id, list_fields, list_views, view, time_range, fields,
            where, select, limit, jq_filter
        )
        self._attach_resume_context(
            result,
            data_id=data_id,
            file_path=data_registry_path,
            list_fields=list_fields,
            list_views=list_views,
            view=view,
            time_range=time_range,
            fields=fields,
            where=where,
            select=select,
            limit=limit,
            jq_filter=jq_filter,
        )
        self._record_read_state(
            result,
            data_id=data_id,
            view=view,
            fields=fields,
            time_range=time_range,
            jq_filter=jq_filter,
            list_fields=list_fields,
            list_views=list_views,
        )
        return result

    def _attach_resume_context(
        self,
        result: Dict[str, Any],
        *,
        data_id: str,
        file_path: Path,
        list_fields: bool,
        list_views: bool,
        view: Optional[str],
        time_range: Optional[str],
        fields: Optional[List[str]],
        where: Optional[Any],
        select: Optional[Any],
        limit: Optional[int],
        jq_filter: Optional[str],
    ) -> None:
        if not isinstance(result, dict) or not result.get("success"):
            return

        result["refs"] = merge_refs(
            result.get("refs"),
            {
                "data": [build_data_ref(data_id, usage="read")],
                "files": [
                    build_file_ref(
                        file_path,
                        type="data",
                        format="json",
                        size=file_path.stat().st_size if file_path.exists() else None,
                        usage="data_registry",
                        data_id=data_id,
                    )
                ],
            },
        )

        read_args = {
            "data_id": data_id,
            "list_fields": list_fields or None,
            "list_views": list_views or None,
            "view": view,
            "time_range": time_range,
            "fields": fields,
            "where": where,
            "select": select,
            "limit": limit,
            "jq_filter": jq_filter,
        }
        compact_args = {key: value for key, value in read_args.items() if value not in (None, False, [], {})}
        data_preview = self._build_data_preview(result.get("data"))
        llm_resume = {
            "tool_hint": self._build_tool_hint(compact_args),
            "read_args": compact_args,
        }
        if data_preview:
            llm_resume["content_preview"] = data_preview
        result["llm_resume"] = llm_resume

    def _build_tool_hint(self, args: Dict[str, Any]) -> str:
        rendered_args = ", ".join(f"{key}={value!r}" for key, value in args.items())
        return f"Use read_data_registry({rendered_args}) to reread this data."

    def _build_data_preview(self, data: Any, max_chars: int = 2000) -> str:
        try:
            preview = json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            preview = str(data)
        if len(preview) <= max_chars:
            return preview
        return f"{preview[:max_chars]}\n...[truncated {len(preview) - max_chars} chars]"

    def _record_read_state(
        self,
        result: Dict[str, Any],
        *,
        data_id: str,
        view: Optional[str],
        fields: Optional[List[str]],
        time_range: Optional[str],
        jq_filter: Optional[str],
        list_fields: bool,
        list_views: bool,
    ) -> None:
        if not isinstance(result, dict) or not result.get("success"):
            return

        try:
            get_data_registry_read_state().set(
                data_id,
                view=view,
                fields=fields,
                time_range=time_range,
                jq_filter=jq_filter,
                list_fields=list_fields,
                list_views=list_views,
                data=result.get("data"),
                metadata=result.get("metadata"),
                summary=result.get("summary"),
            )
            logger.info(
                "data_registry_read_state_recorded",
                data_id=data_id,
                view=view,
                list_fields=list_fields,
                list_views=list_views,
                has_fields=bool(fields),
                has_jq_filter=bool(jq_filter),
            )
        except Exception as exc:
            logger.warning(
                "data_registry_read_state_record_failed",
                data_id=data_id,
                error=str(exc),
            )

    def _resolve_registry_path(self, data_id: str) -> Path:
        entry = data_registry.get_metadata(data_id)
        if entry:
            return Path(entry.dataset_path)

        safe_id = data_id.replace(':', '_')
        candidates = [
            data_registry.datasets_dir / f"{safe_id}.json",
            get_datasets_dir() / f"{safe_id}.json",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    async def _load_from_data_registry(
        self, file_path: Path, data_id: str,
        list_fields: bool = False,
        list_views: bool = False,
        view: Optional[str] = None,
        time_range: Optional[str] = None,
        fields: Optional[List[str]] = None,
        where: Optional[Any] = None,
        select: Optional[Any] = None,
        limit: Optional[int] = None,
        jq_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从 DataRegistry 格式加载数据"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON 解析失败: {str(e)}"}

        if isinstance(data, dict):
            return self._load_report_package(
                data, file_path, data_id, list_fields, list_views, view, fields,
                where, select, limit, jq_filter
            )

        # DataRegistry 直接存储数据数组
        if not isinstance(data, list):
            return {"success": False, "error": f"数据格式错误: 期望数组或对象型报表包，得到 {type(data).__name__}"}

        # 【新增】list_fields 功能：只返回字段列表和时间范围
        if list_fields:
            if data:
                first_record = data[0]
                if isinstance(first_record, dict):
                    # 获取所有字段名（包括嵌套字段）
                    field_list = self._extract_all_fields(first_record)

                    # 【新增】计算时间范围
                    time_range_info = self._calculate_data_time_range(data)

                    # 构建返回数据
                    result_data = {
                        "data_id": data_id,
                        "file_path": str(file_path.resolve()),
                        "total_fields": len(field_list),
                        "fields": field_list,
                        "sample_values": self._get_sample_values(first_record, field_list[:10]),
                        "time_range": time_range_info  # 新增时间范围信息
                    }

                    # 构建摘要信息
                    summary_parts = [f"数据ID {data_id} 包含 {len(field_list)} 个字段"]
                    if time_range_info.get("min_time") and time_range_info.get("max_time"):
                        summary_parts.append(f"，时间范围：{time_range_info['min_time']} ~ {time_range_info['max_time']}")
                        summary_parts.append(f"，共 {time_range_info.get('total_records', len(data))} 条记录")
                    summary = ''.join(summary_parts)

                    return {
                        "success": True,
                        "data": result_data,
                        "summary": summary
                    }
            return {"success": False, "error": "数据为空，无法提取字段"}

        # 应用过滤
        filter_info = {}
        data, filter_info = self._apply_filters(data, time_range, fields, where, select, limit)

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

        mismatch_result = self._build_structured_filter_mismatch_result(data_id, filter_info)
        if mismatch_result:
            return mismatch_result

        # 智能判断：区分聚合操作和明细查询
        is_aggregation = self._is_aggregation_operation(jq_filter, len(data))

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
                    if isinstance(data, list):
                        filter_info["jq_result_count"] = len(data)
                        # jq执行后重新判断是否为聚合
                        is_aggregation = True
                else:
                    # 提供更友好的错误提示
                    error_hint = self._get_jq_error_hint(result.stderr, jq_filter)
                    return {
                        "success": False,
                        "error": f"jq 过滤失败: {result.stderr}",
                        "hint": error_hint
                    }
            except FileNotFoundError:
                filter_info["jq_warning"] = "jq 未安装，跳过 jq 过滤"
            except Exception as e:
                return {"success": False, "error": f"jq 执行失败: {str(e)}"}

        # 记录数限制：只拒绝明细查询，允许聚合结果
        if isinstance(data, list) and len(data) > self.DEFAULT_MAX_RECORDS:
            if not is_aggregation:
                return self._reject_large_detail_result(data, data_id, time_range, fields, jq_filter, filter_info)

        # ✅ 修复：处理 jq_filter 返回的不同类型（聚合操作可能返回 int/str/bool）
        # 检查 data 类型，确定返回记录数
        if isinstance(data, (list, dict)):
            returned_count = len(data)
            data_type = "array" if isinstance(data, list) else "object"
        elif isinstance(data, (int, float, str, bool, type(None))):
            # 聚合操作返回标量值（如 length、sum、max、min 等）
            returned_count = 1  # 标量值算作 1 条记录
            data_type = "scalar"
        else:
            # 其他类型（罕见）
            returned_count = 1
            data_type = type(data).__name__

        return {
            "success": True,
            "file_path": str(file_path),
            "data": data,
            "metadata": {
                "total_records": filter_info.get("original_count", len(data) if isinstance(data, (list, dict)) else 1),
                "returned_records": returned_count,
                "data_type": data_type,  # 新增：标记数据类型
                "filter_applied": bool(filter_info),
                "filter_details": filter_info,
                "source": "data_registry",
                "generator": "read_data_registry",
                "tool_name": "read_data_registry"
            },
            "summary": self._generate_summary(data, filter_info)
        }

    def _load_report_package(
        self,
        package: Dict[str, Any],
        file_path: Path,
        data_id: str,
        list_fields: bool,
        list_views: bool,
        view: Optional[str],
        fields: Optional[List[str]],
        where: Optional[Any],
        select: Optional[Any],
        limit: Optional[int],
        jq_filter: Optional[str],
    ) -> Dict[str, Any]:
        """读取对象型报表数据包。"""
        views = package.get("views")
        if not isinstance(views, dict):
            return {
                "success": False,
                "error": "对象型数据不是有效报表包：缺少 views 字段",
                "data": {
                    "data_id": data_id,
                    "available_top_level_fields": list(package.keys())
                }
            }

        if not list_fields and not list_views and not view and "reporting" in views:
            view = "reporting"

        if list_fields or list_views or not view:
            views_info = {}
            for view_name, view_data in views.items():
                views_info[view_name] = self._describe_view(view_data)

            return {
                "success": True,
                "file_path": str(file_path),
                "data": {
                    "data_id": data_id,
                    "package_kind": package.get("kind", "report_package"),
                    "tool_name": package.get("tool_name"),
                    "query": package.get("query"),
                    "available_views": list(views.keys()),
                    "views": views_info,
                    "metadata": package.get("metadata", {}),
                },
                "metadata": {
                    "data_type": "report_package",
                    "source": "data_registry",
                    "generator": "read_data_registry",
                    "tool_name": "read_data_registry",
                },
                "summary": f"报表数据包 {data_id} 包含视图：{', '.join(views.keys())}"
            }

        if view not in views:
            return {
                "success": False,
                "error": f"视图不存在: {view}",
                "data": {
                    "requested_view": view,
                    "available_views": list(views.keys())
                },
                "summary": f"视图 {view} 不存在，可用视图：{', '.join(views.keys())}"
            }

        data = views[view]

        filter_info: Dict[str, Any] = {}

        if isinstance(data, list):
            data, filter_info = self._apply_filters(data, None, fields, where, select, limit)
            mismatch_result = self._build_structured_filter_mismatch_result(data_id, filter_info)
            if mismatch_result:
                return mismatch_result
        else:
            if fields:
                data = self._select_fields_for_any(data, fields)

        if jq_filter:
            try:
                corrected_filter = self._auto_correct_jq_filter(jq_filter)
                result = subprocess.run(
                    ["jq", corrected_filter],
                    input=json.dumps(data, ensure_ascii=False),
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                else:
                    return {
                        "success": False,
                        "error": f"jq 过滤失败: {result.stderr}",
                        "hint": self._get_jq_error_hint(result.stderr, jq_filter)
                    }
            except FileNotFoundError:
                pass
            except Exception as e:
                return {"success": False, "error": f"jq 执行失败: {str(e)}"}

        returned_count = len(data) if isinstance(data, (list, dict)) else 1
        return {
            "success": True,
            "file_path": str(file_path),
            "data": data,
            "metadata": {
                "data_type": "report_package_view",
                "package_kind": package.get("kind", "report_package"),
                "view": view,
                "returned_records": returned_count,
                "filter_details": filter_info,
                "source": "data_registry",
                "generator": "read_data_registry",
                "tool_name": "read_data_registry",
            },
            "summary": f"已读取报表数据包 {data_id} 的 {view} 视图，返回 {returned_count} 项"
        }

    def _describe_view(self, view_data: Any) -> Dict[str, Any]:
        if isinstance(view_data, list):
            sample = view_data[0] if view_data else {}
            return {
                "type": "array",
                "count": len(view_data),
                "fields": self._extract_all_fields(sample) if isinstance(sample, dict) else [],
                "sample": sample,
            }
        if isinstance(view_data, dict):
            return {
                "type": "object",
                "fields": self._extract_all_fields(view_data),
                "sample": view_data,
            }
        return {
            "type": type(view_data).__name__,
            "sample": view_data,
        }

    def _select_fields_for_any(self, data: Any, fields: List[str]) -> Any:
        if isinstance(data, list):
            selected, _ = self._select_fields(data, fields)
            return selected
        if isinstance(data, dict):
            return self._select_fields_from_record(data, fields)
        return data

    def _is_aggregation_operation(self, jq_filter: Optional[str], data_count: int) -> bool:
        """判断是否为聚合操作

        Args:
            jq_filter: jq过滤表达式
            data_count: 过滤后的数据条数

        Returns:
            True 表示聚合操作，False 表示明细查询
        """
        # 标量值判断
        if data_count == 1:
            return True

        # 没有使用jq_filter，且有大量数据 → 明细查询
        if not jq_filter and data_count > 100:
            return False

        # 使用了jq_filter，检查是否包含聚合关键字
        if jq_filter:
            aggregation_keywords = [
                "group_by", "map(", "select(", "length",
                "add", "max", "min", "avg", "sum", "mean",
                "unique", "sort_by", "first", "last"
            ]
            return any(keyword in jq_filter for keyword in aggregation_keywords)

        # 默认认为是明细查询
        return False

    def _reject_large_detail_result(
        self,
        data: List[Any],
        data_id: str,
        time_range: Optional[str],
        fields: Optional[List[str]],
        jq_filter: Optional[str],
        filter_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """拒绝返回过大的明细数组"""
        returned_count = len(data)

        # 生成简洁的错误提示
        if jq_filter:
            suggestion = f"jq_filter返回{returned_count}条，超过{self.DEFAULT_MAX_RECORDS}条限制。请添加聚合操作如group_by/map/length"
        else:
            suggestion = f"过滤后{returned_count}条，超过{self.DEFAULT_MAX_RECORDS}条限制。请使用jq_filter聚合或缩小time_range"

        return {
            "success": False,
            "error": f"返回{returned_count}条记录，超过{self.DEFAULT_MAX_RECORDS}条限制",
            "data": {
                "error_type": "too_many_records",
                "filtered_records": returned_count,
                "max_records": self.DEFAULT_MAX_RECORDS,
                "time_range": time_range,
                "fields": fields,
                "jq_filter": jq_filter,
                "filter_details": filter_info,
                "suggestion": suggestion,
            },
            "hint": suggestion,
            "summary": f"数据量过大：{returned_count}条 > {self.DEFAULT_MAX_RECORDS}条，请缩小 time_range 或使用聚合查询"
        }

    def _build_structured_filter_mismatch_result(
        self,
        data_id: str,
        filter_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Return a standard-ish failure when structured filters reference missing fields."""
        for info_key, error_type, requested_key in [
            ("where_match_info", "where_field_mismatch", "requested_where_fields"),
            ("select_match_info", "select_field_mismatch", "requested_select_fields"),
        ]:
            match_info = filter_info.get(info_key)
            if not isinstance(match_info, dict) or match_info.get("matched", True):
                continue

            available_fields = match_info.get("available_fields", [])
            mismatched_fields = match_info.get("mismatched_fields", [])
            return {
                "status": "failed",
                "success": False,
                "data": {
                    "error_type": error_type,
                    requested_key: match_info.get("requested_fields", []),
                    "mismatched_fields": mismatched_fields,
                    "available_fields": available_fields,
                    "total_available": len(available_fields),
                    "suggestion": (
                        f"字段 {mismatched_fields} 不存在。请先用 list_views/list_fields 确认字段名，"
                        f"或从可用字段中选择：{', '.join(available_fields[:20])}"
                        f"{'...' if len(available_fields) > 20 else ''}"
                    )
                },
                "metadata": {
                    "tool_name": "read_data_registry",
                    "error": "结构化筛选字段名称不匹配"
                },
                "summary": f"结构化筛选字段名称不匹配：{mismatched_fields}"
            }

        return None

    def _apply_filters(
        self,
        data: List[Dict],
        time_range: Optional[str],
        fields: Optional[List[str]],
        where: Optional[Any] = None,
        select: Optional[Any] = None,
        limit: Optional[int] = None,
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

        # 2. 结构化行筛选
        if where:
            result, where_info = self._filter_by_where(result, where)
            filter_info["where_filter"] = where
            filter_info["where_match_info"] = where_info

        # 3. select取列/别名映射优先于旧版fields
        if select:
            result, select_info = self._select_with_aliases(result, select)
            filter_info["select"] = select
            filter_info["select_match_info"] = select_info
        elif fields:
            result, field_info = self._select_fields(result, fields)
            filter_info["fields_selected"] = fields
            filter_info["field_match_info"] = field_info

        # 4. 明细数量限制
        if isinstance(limit, int) and limit >= 0:
            result = result[:limit]
            filter_info["limit"] = limit

        filter_info["original_count"] = original_count
        filter_info["filtered_count"] = len(result)

        return result, filter_info

    def _filter_by_where(self, data: List[Dict], where: Any) -> tuple[List[Dict], Dict[str, Any]]:
        """Apply structured row filters to list records."""
        conditions = self._normalize_where_conditions(where)
        available_fields = self._available_fields_for_records(data)
        mismatched_fields = [
            condition["field"]
            for condition in conditions
            if available_fields and condition["field"] not in available_fields
        ]
        match_info = {
            "matched": len(mismatched_fields) == 0,
            "requested_fields": [condition["field"] for condition in conditions],
            "mismatched_fields": sorted(set(mismatched_fields)),
            "available_fields": sorted(available_fields),
        }

        if mismatched_fields:
            return data, match_info

        filtered = []
        for record in data:
            if not isinstance(record, dict):
                continue
            if all(self._matches_condition(record, condition) for condition in conditions):
                filtered.append(record)

        match_info["where_count"] = len(filtered)
        return filtered, match_info

    def _normalize_where_conditions(self, where: Any) -> List[Dict[str, Any]]:
        if isinstance(where, dict):
            return [
                {"field": field, "op": "=", "value": value}
                for field, value in where.items()
            ]

        if isinstance(where, list):
            conditions = []
            for item in where:
                if not isinstance(item, dict) or "field" not in item:
                    continue
                conditions.append({
                    "field": item.get("field"),
                    "op": item.get("op", "="),
                    "value": item.get("value"),
                })
            return conditions

        return []

    def _matches_condition(self, record: Dict, condition: Dict[str, Any]) -> bool:
        field = condition.get("field")
        op = str(condition.get("op", "=")).lower()
        expected = condition.get("value")
        actual = self._get_nested_value(record, field)

        if op in {"=", "==", "eq"}:
            return self._values_equal(actual, expected)
        if op in {"!=", "<>", "ne"}:
            return not self._values_equal(actual, expected)
        if op == "in":
            values = expected if isinstance(expected, list) else [expected]
            return any(self._values_equal(actual, value) for value in values)
        if op == "not_in":
            values = expected if isinstance(expected, list) else [expected]
            return not any(self._values_equal(actual, value) for value in values)
        if op == "contains":
            if actual is None:
                return False
            return str(expected) in str(actual)
        if op in {">", ">=", "<", "<="}:
            return self._compare_values(actual, expected, op)

        return self._values_equal(actual, expected)

    def _values_equal(self, actual: Any, expected: Any) -> bool:
        if actual == expected:
            return True
        if actual is None or expected is None:
            return False
        return str(actual) == str(expected)

    def _compare_values(self, actual: Any, expected: Any, op: str) -> bool:
        try:
            actual_num = float(actual)
            expected_num = float(expected)
        except (TypeError, ValueError):
            actual_num = str(actual)
            expected_num = str(expected)

        if op == ">":
            return actual_num > expected_num
        if op == ">=":
            return actual_num >= expected_num
        if op == "<":
            return actual_num < expected_num
        if op == "<=":
            return actual_num <= expected_num
        return False

    def _select_with_aliases(self, data: List[Dict], select: Any) -> tuple[List[Dict], Dict[str, Any]]:
        """Select fields, optionally renaming output keys."""
        if not data:
            return [], {"matched": True, "available_fields": []}

        if isinstance(select, list):
            selected, field_info = self._select_fields(data, select)
            field_info["requested_fields"] = list(select)
            return selected, field_info

        if not isinstance(select, dict):
            return data, {
                "matched": False,
                "requested_fields": [],
                "mismatched_fields": [],
                "available_fields": sorted(self._available_fields_for_records(data)),
                "error": "select 必须是对象或字段数组"
            }

        available_fields = self._available_fields_for_records(data)
        requested_fields = list(select.values())
        mismatched_fields = [
            field for field in requested_fields
            if available_fields and field not in available_fields
        ]

        field_info = {
            "matched": len(mismatched_fields) == 0,
            "requested_fields": requested_fields,
            "mismatched_fields": sorted(set(mismatched_fields)),
            "available_fields": sorted(available_fields),
            "aliases": select,
        }
        if mismatched_fields:
            return data, field_info

        selected = []
        for record in data:
            if not isinstance(record, dict):
                selected.append(record)
                continue
            selected_record = {}
            for output_name, source_field in select.items():
                selected_record[output_name] = self._get_nested_value(record, source_field)
            selected.append(selected_record)

        return selected, field_info

    def _available_fields_for_records(self, data: List[Dict]) -> List[str]:
        if not data:
            return []
        first_record = data[0] if isinstance(data[0], dict) else {}
        return self._extract_all_fields(first_record) if isinstance(first_record, dict) else []

    def _get_nested_value(self, record: Dict, field_path: str) -> Any:
        if not isinstance(record, dict) or not field_path:
            return None
        current: Any = record
        for part in str(field_path).split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

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
        elif isinstance(data, dict):
            # 字典类型
            total = filter_info.get("original_count", 1)
            return f"数据内容: 1 个对象（字典）"
        elif isinstance(data, (int, float)):
            # 聚合操作返回数字（如 length、sum、max、min 等）
            jq_used = filter_info.get("jq_filter", "")
            if "length" in jq_used:
                return f"聚合结果: {data} 条记录（jq: {jq_used}）"
            else:
                return f"聚合结果: {data}（jq: {jq_used}）"
        elif isinstance(data, str):
            return f"聚合结果: '{data}'"
        elif isinstance(data, bool):
            return f"聚合结果: {data}"
        else:
            # 其他类型（fallback）
            try:
                return f"数据内容: {json.dumps(data, ensure_ascii=False)[:200]}"
            except:
                return f"数据内容: {str(data)[:200]}"

    def _auto_correct_jq_filter(self, jq_filter: str) -> str:
        """智能修正 jq 过滤表达式（只修正最简单的错误）"""
        jq_filter = jq_filter.strip()

        # 如果已经包含任何函数或操作符，说明用户知道如何使用
        if any(keyword in jq_filter for keyword in
               [".[]", "map(", "select(", "group_by", "length", "add", "max", "min", "|"]):
            return jq_filter

        # 只修正最基本的错误：直接访问字段
        if jq_filter.startswith(".") and "|" not in jq_filter:
            return f"map({jq_filter})"

        return jq_filter

    def _calculate_data_time_range(self, data: List[Dict]) -> Dict[str, Any]:
        """计算数据的时间范围

        返回格式：
        {
            "time_field": "timestamp",
            "min_time": "2024-01-01 00:00:00",
            "max_time": "2024-12-31 23:00:00",
            "count": 8760
        }
        """
        if not data:
            return {
                "time_field": None,
                "min_time": None,
                "max_time": None,
                "count": 0,
                "message": "数据为空"
            }

        # 查找时间字段
        time_field = self._find_time_field(data)
        if not time_field:
            return {
                "time_field": None,
                "min_time": None,
                "max_time": None,
                "count": len(data),
                "message": f"未找到时间字段，尝试的字段: {self.TIME_FIELDS}"
            }

        # 提取所有时间值
        times = []
        for record in data:
            time_val = record.get(time_field)
            if time_val is not None:
                times.append(str(time_val))

        if times:
            # 排序以获取最小最大值
            sorted_times = sorted(times)
            return {
                "time_field": time_field,
                "min_time": sorted_times[0],
                "max_time": sorted_times[-1],
                "count": len(times),
                "total_records": len(data)
            }
        else:
            return {
                "time_field": time_field,
                "min_time": None,
                "max_time": None,
                "count": 0,
                "total_records": len(data),
                "message": "时间字段存在但无有效值"
            }

    def _get_jq_error_hint(self, stderr: str, jq_filter: str) -> str:
        """根据 jq 错误信息提供简洁提示"""
        if "Cannot index array" in stderr:
            return "数组需要使用 .[] 或 map/select 函数"
        elif "syntax error" in stderr:
            return "jq语法错误"
        else:
            return ""


# 工具注册
tool = ReadDataRegistryTool()
