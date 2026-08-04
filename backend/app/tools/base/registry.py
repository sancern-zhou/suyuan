"""
Tool Registry - 单一工具注册源

统一管理所有LLM工具，提供：
1. 单一注册源：所有工具在一个地方注册
2. 元数据自动生成：Function Schema、返回Schema、测试样例
3. 数据规范校验：确保输出符合UDF v1.0和v3.0图表规范
4. 性能监控：调用统计、失败率、响应时间
"""
from typing import Dict, List, Optional, Any, Type, Union
from datetime import datetime
import structlog

# 导入工具类别枚举
from app.tools.base.tool_interface import ToolCategory

logger = structlog.get_logger()


class ToolRegistry:
    """单一工具注册表 - 统一管理所有LLM工具

    特点：
    1. 单一注册源：所有工具在一个地方注册
    2. 元数据完整：自动生成 Function Schema、返回Schema、测试样例
    3. 数据规范：确保输出符合统一数据格式(UDF v1.0)和v3.0图表规范
    4. 自动化：减少重复劳动，提升开发效率
    """

    def __init__(self, registry_name: str = "default"):
        self.registry_name = registry_name
        self._tools: Dict[str, Any] = {}
        self._priority_order: List[tuple] = []  # [(priority, tool_name), ...]
        self._stats: Dict[str, Dict[str, int]] = {}
        self._metadata_generators = {}  # 存储元数据生成器

    def register(
        self,
        tool,
        priority: int = 100,
        input_adapter_rules: Optional[Dict[str, Any]] = None,
        return_schema: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_generate: bool = True
    ):
        """
        注册工具 - 单一注册源

        自动化特性：
        1. 自动生成 Function Schema（如果未提供）
        2. 自动生成返回Schema（如果未提供）
        3. 自动生成测试样例
        4. 自动验证符合统一数据格式规范

        Args:
            tool: 工具实例（必须继承LLMTool）
            priority: 优先级（数字越小优先级越高，范围1-1000）
            input_adapter_rules: 已废弃；保留参数仅兼容旧调用，不再存储或使用
            return_schema: 返回数据Schema（Pydantic模型或JSON Schema）
                - 确保输出符合UDF v1.0统一数据格式
                - 确保图表输出符合v3.0规范
            metadata: 工具元数据
                - requires_handle: 是否需要数据句柄
                - supports_batch: 是否支持批量处理
                - category: 工具类别（query/analysis/visualization）
                - data_type: 主要数据类型
                - description: 详细描述
            auto_generate: 是否自动生成缺失的元数据
        """
        tool_name = tool.name

        if tool_name in self._tools:
            logger.error(
                "tool_duplicate_registration",
                registry=self.registry_name,
                tool=tool_name
            )
            raise ValueError(f"工具 {tool_name} 已存在，不允许重复注册")

        # 自动生成缺失的元数据
        if auto_generate:
            if not return_schema:
                return_schema = self._generate_return_schema(tool)
            if not metadata:
                metadata = self._generate_tool_metadata(tool)

        # 参数契约由原生 tool schema 提供，不再生成或存储输入适配规则。
        input_adapter_rules = {}

        if not return_schema:
            logger.warning(
                "tool_no_return_schema",
                tool=tool_name,
                message="建议提供返回Schema以确保数据格式一致"
            )
            return_schema = {}

        # ✅ 验证工具 Schema（防止 "unknown" 工具问题）
        try:
            function_schema = tool.get_function_schema()
            schema_name = function_schema.get("name")

            if not schema_name or not isinstance(schema_name, str) or not schema_name.strip():
                logger.error(
                    "tool_schema_invalid_name",
                    tool=tool_name,
                    schema_name=schema_name,
                    schema_preview=str(function_schema)[:200],
                    message="工具 Schema 缺少有效的 name 字段，拒绝注册"
                )
                raise ValueError(f"工具 {tool_name} 的 Schema 缺少有效的 name 字段")

            # 确保 schema 的 name 与 tool.name 一致
            if schema_name != tool_name:
                logger.warning(
                    "tool_schema_name_mismatch",
                    tool=tool_name,
                    schema_name=schema_name,
                    message="Schema name 与 tool.name 不一致，使用 tool.name"
                )

        except Exception as e:
            logger.error(
                "tool_schema_validation_failed",
                tool=tool_name,
                error=str(e),
                message="无法获取或验证工具 Schema，拒绝注册"
            )
            raise

        # 存储工具及完整元数据
        tool_data = {
            "tool": tool,
            "priority": priority,
            "return_schema": return_schema,
            "metadata": metadata or {},
            "registered_at": datetime.now().isoformat(),
            "version": getattr(tool, 'version', '1.0.0'),
            "category": getattr(tool, 'category', None),
            "requires_context": getattr(tool, 'requires_context', False)
        }

        self._tools[tool_name] = tool_data
        self._priority_order.append((priority, tool_name))
        self._priority_order.sort(key=lambda x: x[0])  # 按优先级排序

        # 初始化统计
        self._stats[tool_name] = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "reflexion_attempts": 0,
            "avg_execution_time": 0.0
        }

        # 生成测试样例
        test_samples = self._generate_test_samples(tool, tool_data)
        tool_data["test_samples"] = test_samples

        logger.info(
            "tool_registered",
            registry=self.registry_name,
            tool=tool_name,
            priority=priority,
            has_adapter=False,
            has_schema=bool(return_schema),
            category=tool_data.get("category"),
            requires_context=tool_data.get("requires_context")
        )

    def unregister(self, tool_name: str):
        """注销工具"""
        if tool_name in self._tools:
            del self._tools[tool_name]
            self._priority_order = [
                (p, name) for p, name in self._priority_order
                if name != tool_name
            ]

            logger.info(
                "tool_unregistered",
                registry=self.registry_name,
                tool=tool_name
            )

    def get_tool(self, tool_name: str):
        """获取指定工具"""
        tool_data = self._tools.get(tool_name)
        return tool_data["tool"] if tool_data else None

    def get_tool_data(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取工具完整数据（工具+Schema+元数据）"""
        return self._tools.get(tool_name)

    def get_input_adapter(self, tool_name: str) -> Dict[str, Any]:
        """输入适配已废弃；保留空返回兼容旧调用。"""
        return {}

    def get_input_adapter_rules(self, tool_name: str) -> Dict[str, Any]:
        """输入适配已废弃；保留空返回兼容旧调用。"""
        return {}

    def get_return_schema(self, tool_name: str) -> Dict[str, Any]:
        """获取工具返回Schema"""
        tool_data = self._tools.get(tool_name)
        return tool_data.get("return_schema", {}) if tool_data else {}

    def get_metadata(self, tool_name: str) -> Dict[str, Any]:
        """获取工具元数据"""
        tool_data = self._tools.get(tool_name)
        return tool_data.get("metadata", {}) if tool_data else {}

    def list_tools(self) -> List[str]:
        """列出所有工具（按优先级排序）"""
        return [name for _, name in self._priority_order]

    def get_all_tools(self) -> List[Any]:
        """获取所有工具实例（按优先级排序）"""
        return [self._tools[name] for _, name in self._priority_order if name in self._tools]

    def get_function_schemas(self) -> List[Dict[str, Any]]:
        """获取所有工具的Function Calling定义"""
        schemas = []
        for tool_name, tool_data in self._tools.items():
            tool = tool_data["tool"]
            if tool.is_available():
                schemas.append(tool.get_function_schema())
        return schemas

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """获取统计信息"""
        return self._stats

    def record_success(self, tool_name: str):
        """记录成功"""
        if tool_name in self._stats:
            self._stats[tool_name]["total"] += 1
            self._stats[tool_name]["success"] += 1

    def record_failure(self, tool_name: str):
        """记录失败"""
        if tool_name in self._stats:
            self._stats[tool_name]["total"] += 1
            self._stats[tool_name]["failed"] += 1

    async def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """
        执行指定工具（带性能监控）

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            Any: 工具执行结果
        """
        tool_data = self._tools.get(tool_name)
        if not tool_data:
            logger.error("tool_not_found", tool=tool_name)
            return None

        start_time = datetime.now()
        tool = tool_data["tool"]
        try:
            result = await tool.run(**kwargs)
            execution_time = (datetime.now() - start_time).total_seconds()

            # 更新统计信息
            self.record_success(tool_name)
            self._update_execution_time(tool_name, execution_time)

            logger.info(
                "tool_executed_successfully",
                tool=tool_name,
                execution_time=execution_time
            )
            return result
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            self.record_failure(tool_name)
            logger.error(
                "tool_execution_failed",
                tool=tool_name,
                error=str(e),
                execution_time=execution_time
            )
            return None

    # ========================================
    # 自动元数据生成方法
    # ========================================

    def _generate_return_schema(self, tool) -> Dict[str, Any]:
        """
        自动生成返回Schema（基于工具类别）

        确保输出符合：
        - UDF v1.0 统一数据格式（status, success, data, metadata, summary）
        - v3.0 图表规范（如果工具生成图表）
        """
        category = getattr(tool, 'category', None)
        tool_name = tool.name

        if not category:
            return self._get_default_return_schema()

        # 根据工具类别返回不同Schema
        if category == ToolCategory.QUERY:
            schema = {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["success", "failed", "partial", "empty"]
                    },
                    "success": {"type": "boolean"},
                    "data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "station_code": {"type": "string"},
                                "station_name": {"type": "string"},
                                "timestamp": {"type": "string", "format": "date-time"},
                                "value": {"type": "number"},
                                "unit": {"type": "string"}
                            }
                        }
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "data_type": {"type": "string"},
                            "record_count": {"type": "integer"},
                            "source": {"type": "string"}
                        }
                    },
                    "summary": {"type": "string"}
                },
                "required": ["status", "success", "data", "metadata", "summary"]
            }
            return schema
        elif category == ToolCategory.ANALYSIS:
            schema = {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["success", "failed", "partial", "empty"]
                    },
                    "success": {"type": "boolean"},
                    "data": {"type": "object"},  # 添加data字段
                    "file_path": {"type": "string"},
                    "summary": {"type": "string"},
                    "detailed_summary": {"type": "string"},
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "analysis_type": {"type": "string"},
                            "source_data": {"type": "string"},
                            "model_version": {"type": "string"}
                        }
                    }
                },
                "required": ["status", "success", "data", "metadata", "summary"]
            }
            return schema
        elif category == ToolCategory.VISUALIZATION:
            # v3.0 图表规范
            schema = {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["success", "failed", "partial", "empty"]
                    },
                    "success": {"type": "boolean"},
                    "visuals": {"type": "array", "items": {"type": "object"}},
                    "file_path": {"type": "string"},
                    "source_file_path": {"type": "string"},
                    "detailed_summary": {"type": "string"},
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "chart_id": {"type": "string"},
                            "chart_type": {"type": "string"},
                            "source_file_path": {"type": "string"}
                        }
                    },
                    "summary": {"type": "string"}
                },
                "required": ["status", "success", "visuals", "metadata", "summary"]
            }
            return schema
        else:
            return self._get_default_return_schema()

    def _get_default_return_schema(self) -> Dict[str, Any]:
        """默认返回Schema（符合UDF v1.0）"""
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["success", "failed", "partial", "empty"]
                },
                "success": {"type": "boolean"},
                "data": {"type": "array", "items": {"type": "object"}},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "data_type": {"type": "string"},
                        "record_count": {"type": "integer"}
                    }
                },
                "summary": {"type": "string"}
            },
            "required": ["status", "success", "data", "metadata", "summary"]
        }

    def _generate_tool_metadata(self, tool) -> Dict[str, Any]:
        """生成工具元数据"""
        category = getattr(tool, 'category', None)
        tool_name = tool.name
        requires_context = getattr(tool, 'requires_context', False)

        metadata = {
            "name": tool_name,
            "description": getattr(tool, 'description', ''),
            "version": getattr(tool, 'version', '1.0.0'),
            "requires_context": requires_context
        }

        # 根据工具名称推断数据类型
        if "pmf" in tool_name:
            metadata["data_type"] = "pmf_result"
            metadata["requires_handle"] = True
        elif "obm" in tool_name or "ofp" in tool_name:
            metadata["data_type"] = "obm_ofp_result"
            metadata["requires_handle"] = True
        elif "component" in tool_name or "voc" in tool_name:
            metadata["data_type"] = "vocs_unified"
            metadata["requires_handle"] = False
        elif "weather" in tool_name:
            metadata["data_type"] = "weather"
            metadata["requires_handle"] = False
        elif "air_quality" in tool_name:
            metadata["data_type"] = "air_quality"
            metadata["requires_handle"] = False
        elif "chart" in tool_name or "map" in tool_name:
            metadata["data_type"] = "chart_config"
            metadata["requires_handle"] = True
        else:
            metadata["data_type"] = "unified"
            metadata["requires_handle"] = False

        # 批量处理支持
        if category == ToolCategory.QUERY:
            metadata["supports_batch"] = True
        else:
            metadata["supports_batch"] = False

        return metadata

    def _generate_test_samples(self, tool, tool_data: Dict) -> List[Dict]:
        """生成测试样例"""
        tool_name = tool.name
        schema = tool.get_function_schema()
        properties = schema.get('parameters', {}).get('properties', {})

        samples = []

        # 基础正常用例
        normal_sample = {
            "name": "normal_case",
            "description": "正常输入测试",
            "args": {}
        }

        # 根据字段类型生成样例
        for field_name, field_config in properties.items():
            sample_value = self._generate_sample_value(field_name, field_config)
            if sample_value is not None:
                normal_sample["args"][field_name] = sample_value

        if normal_sample["args"]:
            samples.append(normal_sample)

        # 边界情况测试
        edge_sample = {
            "name": "edge_case",
            "description": "边界值测试",
            "args": {}
        }

        for field_name, field_config in properties.items():
            edge_value = self._generate_edge_value(field_name, field_config)
            if edge_value is not None:
                edge_sample["args"][field_name] = edge_value

        if edge_sample["args"]:
            samples.append(edge_sample)

        return samples

    def _generate_sample_value(self, field_name: str, field_config: Dict) -> Any:
        """生成字段样例值"""
        field_type = field_config.get("type", "string")

        if field_type == "string":
            if "city" in field_name.lower():
                return "广州"
            elif "question" in field_name.lower():
                return "查询广州昨日小时空气质量"
            elif "file_path" in field_name:
                return "/data/sessions/example/data/air_quality--example.json"
            else:
                return "test_value"
        elif field_type == "number":
            if "lat" in field_name:
                return 23.1291  # 广州纬度
            elif "lon" in field_name:
                return 113.2644  # 广州经度
            else:
                return 100
        elif field_type == "array":
            return []
        elif field_type == "object":
            return {}

        return None

    def _generate_edge_value(self, field_name: str, field_config: Dict) -> Any:
        """生成边界测试值"""
        field_type = field_config.get("type", "string")

        if field_type == "number":
            if "lat" in field_name:
                return 0  # 赤道
            elif "lon" in field_name:
                return 0  # 本初子午线
            else:
                return field_config.get("minimum", 0)
        elif field_type == "string":
            return ""  # 空字符串

        return None

    def _update_execution_time(self, tool_name: str, execution_time: float):
        """更新平均执行时间（EWMA）"""
        if tool_name in self._stats:
            current_avg = self._stats[tool_name].get("avg_execution_time", 0.0)
            alpha = 0.1  # 平滑因子
            new_avg = alpha * execution_time + (1 - alpha) * current_avg
            self._stats[tool_name]["avg_execution_time"] = new_avg

    # ========================================
    # 验证和合规检查
    # ========================================

    def validate_tool_compliance(self, tool_name: str) -> Dict[str, Any]:
        """
        验证工具是否符合统一数据格式和v3.0规范

        Returns:
            验证结果字典
        """
        tool_data = self._tools.get(tool_name)
        if not tool_data:
            return {"valid": False, "error": "工具不存在"}

        results = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        # 检查是否有返回Schema
        if not tool_data.get("return_schema"):
            results["warnings"].append("建议添加返回Schema以确保数据格式一致")

        # 检查元数据完整性
        metadata = tool_data.get("metadata", {})
        required_meta_fields = ["data_type"]
        for field in required_meta_fields:
            if field not in metadata:
                results["errors"].append(f"缺少必要元数据字段: {field}")

        # 检查测试样例
        if not tool_data.get("test_samples"):
            results["warnings"].append("建议添加测试样例")

        results["valid"] = len(results["errors"]) == 0
        return results

    # ========================================
    # 工具/技能管理功能（新增）
    # ========================================

    def get_tools_info(self) -> List[Dict[str, Any]]:
        """
        获取所有工具的详细信息（用于前端展示）

        Returns:
            工具信息列表
        """
        tools_info = []
        for tool_name, tool_data in self._tools.items():
            tool = tool_data["tool"]
            stats = self._stats.get(tool_name, {})
            metadata = tool_data.get("metadata", {})

            # 获取工具状态（安全访问，非 LLMTool 可能没有 enabled 属性）
            is_enabled = getattr(tool, 'enabled', True)
            tool_desc = getattr(tool, 'description', '')

            tool_status = {
                "name": tool_name,
                "description": tool_desc,
                "category": tool_data.get("category", "unknown"),
                "status": "enabled" if is_enabled else "disabled",
                "version": tool_data.get("version", "1.0.0"),
                "requires_context": tool_data.get("requires_context", False),
                "priority": tool_data.get("priority", 100),
                "registered_at": tool_data.get("registered_at"),
                "statistics": {
                    "total": stats.get("total", 0),
                    "success": stats.get("success", 0),
                    "failed": stats.get("failed", 0),
                    "avg_execution_time": stats.get("avg_execution_time", 0.0)
                },
                "metadata": {
                    "data_type": metadata.get("data_type", "unknown"),
                    "supports_batch": metadata.get("supports_batch", False),
                    "requires_handle": metadata.get("requires_handle", False)
                }
            }
            tools_info.append(tool_status)

        return tools_info

    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取单个工具的详细信息

        Args:
            tool_name: 工具名称

        Returns:
            工具信息字典，不存在则返回None
        """
        tool_data = self._tools.get(tool_name)
        if not tool_data:
            return None

        tool = tool_data["tool"]
        stats = self._stats.get(tool_name, {})
        metadata = tool_data.get("metadata", {})

        # 安全获取工具属性
        is_enabled = getattr(tool, 'enabled', True)
        tool_desc = getattr(tool, 'description', '')

        # 获取Function Schema（参数定义）
        function_schema = None
        if hasattr(tool, 'get_function_schema'):
            function_schema = tool.get_function_schema()

        return {
            "name": tool_name,
            "description": tool_desc,
            "category": tool_data.get("category", "unknown"),
            "status": "enabled" if is_enabled else "disabled",
            "version": tool_data.get("version", "1.0.0"),
            "requires_context": tool_data.get("requires_context", False),
            "priority": tool_data.get("priority", 100),
            "registered_at": tool_data.get("registered_at"),
            "statistics": {
                "total": stats.get("total", 0),
                "success": stats.get("success", 0),
                "failed": stats.get("failed", 0),
                "avg_execution_time": stats.get("avg_execution_time", 0.0)
            },
            "metadata": {
                "data_type": metadata.get("data_type", "unknown"),
                "supports_batch": metadata.get("supports_batch", False),
                "requires_handle": metadata.get("requires_handle", False)
            },
            "function_schema": function_schema,
            "has_input_adapter": False,
            "has_return_schema": bool(tool_data.get("return_schema"))
        }

    def set_tool_enabled(self, tool_name: str, enabled: bool) -> bool:
        """
        设置工具启用/禁用状态

        Args:
            tool_name: 工具名称
            enabled: True=启用, False=禁用

        Returns:
            bool: 操作是否成功
        """
        tool_data = self._tools.get(tool_name)
        if not tool_data:
            return False

        tool = tool_data["tool"]

        # 检查是否有 enable/disable 方法
        if hasattr(tool, 'enable') and hasattr(tool, 'disable'):
            if enabled:
                tool.enable()
            else:
                tool.disable(reason="Admin disabled")
        elif hasattr(tool, 'enabled'):
            # 对于有 enabled 属性但没有 enable/disable 方法的工具，直接设置属性
            tool.enabled = enabled

        return True

    def get_tool_status(self, tool_name: str) -> Optional[str]:
        """
        获取工具状态

        Args:
            tool_name: 工具名称

        Returns:
            str: "enabled" 或 "disabled"，不存在则返回None
        """
        tool_data = self._tools.get(tool_name)
        if not tool_data:
            return None

        tool = tool_data["tool"]
        # 安全访问 enabled 属性
        is_enabled = getattr(tool, 'enabled', True)
        return "enabled" if is_enabled else "disabled"

    def get_tools_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        按类别获取工具列表

        Args:
            category: 工具类别 (query/analysis/visualization/task_management)

        Returns:
            该类别的工具信息列表
        """
        all_tools = self.get_tools_info()
        return [t for t in all_tools if t["category"] == category]

    def get_categories(self) -> List[str]:
        """
        获取所有工具类别

        Returns:
            类别列表
        """
        categories = set()
        for tool_data in self._tools.values():
            cat = tool_data.get("category")
            if cat:
                categories.add(cat)
        return sorted(list(categories))
