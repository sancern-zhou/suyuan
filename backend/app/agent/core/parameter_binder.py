"""
智能参数绑定器 (ParameterBinder)

职责：动态解析绑定表达式，从工具结果中提取参数值
- 支持索引访问：tool_name[0]
- 支持字段访问：tool_name[0].field_name 或 tool_name[0].nested.field
- 支持上下文引用：{location}, {auto_generate}
- 支持通配符：weather:*, component:*
"""

from typing import Dict, List, Any, Optional, Union
import re
import structlog
from .tool_dependencies import (
    BINDING_EXPRESSION_PATTERNS,
    TOOL_DEPENDENCY_GRAPHS,
    TOOL_OUTPUT_SCHEMAS
)

logger = structlog.get_logger()


class ParameterBindingError(Exception):
    """参数绑定异常"""
    pass


class ToolResult:
    """工具执行结果包装器"""

    def __init__(self, tool_name: str, index: int, result: Dict[str, Any], role: Optional[str] = None):
        self.tool_name = tool_name
        self.index = index
        self.result = result
        self.role = role  # 工具角色标识（如 water-soluble, carbon, crustal, trace）
        # 【修复】从metadata中提取data_id（如果顶层没有）
        self.data_id = result.get("data_id")
        if not self.data_id and "metadata" in result:
            metadata = result["metadata"]
            if isinstance(metadata, dict):
                self.data_id = metadata.get("data_id")
        self.metadata = result.get("metadata", {})
        self.data = result.get("data")
        self.success = result.get("success", True)

    def get_field(self, field_path: str) -> Any:
        """获取字段值，支持嵌套路径和metadata访问"""
        try:
            # 【修复】首先尝试从result中获取字段
            current = self.result

            # 如果字段路径是"data_id"，特殊处理：尝试从metadata.data_id获取
            if field_path == "data_id":
                # 首先尝试从顶层获取
                top_level_value = current.get("data_id")
                if top_level_value is not None:
                    return top_level_value
                # 如果顶层没有，尝试从metadata中获取
                if "metadata" in current:
                    metadata = current["metadata"]
                    if isinstance(metadata, dict):
                        return metadata.get("data_id")
                # 都没有，返回None
                return None

            # 处理其他字段的嵌套访问
            for part in field_path.split("."):
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None
            return current
        except Exception as e:
            logger.warning(
                "field_access_failed",
                tool=self.tool_name,
                index=self.index,
                field_path=field_path,
                error=str(e)
            )
            return None

    def __repr__(self) -> str:
        return f"ToolResult({self.tool_name}[{self.index}], success={self.success})"


class ParameterBinder:
    """智能参数绑定器"""

    def __init__(self):
        """初始化参数绑定器"""
        self.binding_patterns = BINDING_EXPRESSION_PATTERNS
        self.dependency_graphs = TOOL_DEPENDENCY_GRAPHS
        self.output_schemas = TOOL_OUTPUT_SCHEMAS
        logger.info("parameter_binder_initialized")

    def bind_parameters(
        self,
        tool_name: str,
        input_bindings: Dict[str, Any],
        context: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> Dict[str, Any]:
        """
        【修复】为指定工具绑定参数，并输出详细日志

        Args:
            tool_name: 工具名称
            input_bindings: 输入绑定配置
            context: 执行上下文
            tool_results: 已执行工具的结果列表

        Returns:
            绑定后的参数字典
        """
        bound_params = {}

        # 【新增】输出参数绑定开始信息
        logger.info(
            "parameter_binding_start",
            tool=tool_name,
            input_bindings_count=len(input_bindings),
            input_bindings={
                k: (str(v)[:50] if len(str(v)) > 50 else v)
                for k, v in input_bindings.items()
            },
            context_keys=list(context.keys()),
            tool_results_count=len(tool_results)
        )

        for param_name, binding_expr in input_bindings.items():
            try:
                # 如果binding_expr不是字符串，直接返回（非绑定表达式）
                if not isinstance(binding_expr, str):
                    bound_params[param_name] = binding_expr
                    logger.debug(
                        "parameter_passed_directly",
                        tool=tool_name,
                        param=param_name,
                        value=binding_expr,
                        type=type(binding_expr).__name__
                    )
                    continue

                # 解析绑定表达式
                parsed = self._parse_binding_expression(binding_expr)

                # 【修复】根据表达式类型解析值
                if parsed["type"] == "indexed_tool":
                    value = self._resolve_indexed_tool(parsed, tool_results)
                elif parsed["type"] == "role_based_tool":
                    value = self._resolve_role_based_tool(parsed, tool_results)
                elif parsed["type"] == "role_based_field":
                    value = self._resolve_role_based_field(parsed, tool_results)
                elif parsed["type"] == "field_access":
                    value = self._resolve_field_access(parsed, tool_results)
                elif parsed["type"] == "simple_index_field_access":
                    value = self._resolve_simple_index_field_access(parsed, tool_results)
                elif parsed["type"] == "context_field":
                    # 【修复】context_field 和 special_value 正则相同，优先尝试从context获取
                    # 如果context中不存在，尝试作为特殊值解析
                    field_name = parsed["groups"][0]
                    if field_name in context:
                        value = context[field_name]
                    else:
                        # context中不存在，尝试作为特殊值解析
                        enriched_context = dict(context)
                        enriched_context["tool_results"] = tool_results
                        # 构造一个模拟的special_value解析结果
                        special_parsed = {
                            "type": "special_value",
                            "groups": (field_name,),
                            "pattern": parsed["pattern"],
                            "description": parsed["description"]
                        }
                        value = self._resolve_special_value(special_parsed, enriched_context)
                elif parsed["type"] == "context_nested":
                    value = self._resolve_context_nested(parsed, context)
                elif parsed["type"] == "wildcard":
                    value = self._resolve_wildcard(parsed, tool_results)
                elif parsed["type"] == "special_value":
                    # 【修复】将tool_results传入context，以便特殊值解析器可以访问
                    enriched_context = dict(context)
                    enriched_context["tool_results"] = tool_results
                    value = self._resolve_special_value(parsed, enriched_context)
                elif parsed["type"] == "literal_value":
                    # 【新增】直接值类型，直接返回原值
                    value = binding_expr
                elif parsed["type"] == "first_matching_tool":
                    value = self._resolve_first_matching_tool(parsed, tool_results)
                elif parsed["type"] == "first_matching_field":
                    value = self._resolve_first_matching_field(parsed, tool_results)
                elif parsed["type"] == "fallback_field":
                    value = self._resolve_fallback_field(parsed, tool_results, context)
                elif parsed["type"] == "simple_index":
                    value = self._resolve_simple_index(parsed, tool_results)
                else:
                    # 【修复】未匹配的表达式，保留原值而不是设置为None
                    value = binding_expr

                bound_params[param_name] = value

                logger.debug(
                    "parameter_bound",
                    tool=tool_name,
                    param=param_name,
                    expression=binding_expr,
                    value=str(value)[:100]
                )

            except ParameterBindingError as e:
                logger.error(
                    "parameter_binding_failed",
                    tool=tool_name,
                    param=param_name,
                    expression=binding_expr,
                    error=str(e)
                )
                # 绑定失败时使用默认值或跳过
                bound_params[param_name] = None

            except Exception as e:
                logger.error(
                    "parameter_binding_error",
                    tool=tool_name,
                    param=param_name,
                    expression=binding_expr,
                    error=str(e)
                )
                bound_params[param_name] = None

        # 【新增】输出参数绑定完成信息，包括前后对比
        logger.info(
            "parameter_binding_completed",
            tool=tool_name,
            input_bindings={
                k: (str(v)[:50] if len(str(v)) > 50 else v)
                for k, v in input_bindings.items()
            },
            bound_params={
                k: (str(v)[:50] if len(str(v)) > 50 else v)
                for k, v in bound_params.items()
            },
            total_params=len(bound_params),
            success_ratio=f"{len([v for v in bound_params.values() if v is not None])}/{len(bound_params)}"
        )

        return bound_params

    def _parse_binding_expression(self, expression: str) -> Dict[str, Any]:
        """解析绑定表达式"""
        for pattern_name, pattern_info in self.binding_patterns.items():
            match = re.match(pattern_info["pattern"], expression)
            if match:
                return {
                    "type": pattern_name,
                    "pattern": pattern_info["pattern"],
                    "groups": match.groups(),
                    "description": pattern_info["description"]
                }

        # 未匹配任何模式
        logger.warning(
            "unmatched_binding_expression",
            expression=expression
        )
        return {
            "type": "unknown",
            "pattern": None,
            "groups": (),
            "description": "未匹配的表达式"
        }

    def _resolve_indexed_tool(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> ToolResult:
        """解析索引工具引用，如: get_component_data[0]"""
        tool_name = parsed["groups"][0]
        index = int(parsed["groups"][1])

        # 查找匹配的工具结果
        for result in tool_results:
            if result.tool_name == tool_name and result.index == index:
                return result

        raise ParameterBindingError(
            f"未找到工具 {tool_name}[{index}] 的执行结果"
        )

    def _resolve_role_based_tool(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> ToolResult:
        """
        解析按角色引用的工具结果，如: get_particulate_data[role=water-soluble]

        这种方式不依赖工具的执行顺序，而是根据工具的role属性匹配
        解决了因工具执行失败导致的索引偏移问题
        """
        tool_name = parsed["groups"][0]
        role = parsed["groups"][1]

        # 查找匹配的工具结果
        for result in tool_results:
            if result.tool_name == tool_name and result.role == role and result.success:
                logger.debug(
                    "found_role_based_tool",
                    tool=tool_name,
                    role=role,
                    index=result.index,
                    data_id=result.data_id
                )
                return result

        raise ParameterBindingError(
            f"未找到工具 {tool_name}[role={role}] 的成功执行结果"
        )

    def _resolve_role_based_field(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> Any:
        """
        解析按角色访问工具结果字段，如: get_particulate_data[role=water-soluble].data_id

        这种方式不依赖工具的执行顺序，而是根据工具的role属性匹配后访问字段
        解决了因工具执行失败导致的索引偏移问题
        """
        tool_name = parsed["groups"][0]
        role = parsed["groups"][1]
        field_path = parsed["groups"][2]

        # 查找匹配的工具结果
        tool_result = self._resolve_role_based_tool(parsed, tool_results)

        # 获取字段值
        value = tool_result.get_field(field_path)

        if value is None:
            raise ParameterBindingError(
                f"工具 {tool_name}[role={role}] 中未找到字段 {field_path}"
            )

        logger.debug(
            "role_based_field_accessed",
            tool=tool_name,
            role=role,
            field=field_path,
            value=str(value)[:100]
        )

        return value

    def _resolve_field_access(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> Any:
        """解析字段访问，支持: get_component_data[0].data_id 和 $2.payload.data.analyzed_stations[0]"""
        groups = parsed["groups"]

        # 根据正则表达式结构:
        # pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]\.([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?)*)$"
        # 对于 "get_particulate_data[2].data_id":
        #   groups[0] = "get_particulate_data" (第一个捕获组: 工具名)
        #   groups[1] = "2" (第二个捕获组: 索引)
        #   groups[2] = "data_id" (第三个捕获组: 字段路径)
        #
        # 对于 "get_particulate_data[2].metadata.station_name":
        #   groups[0] = "get_particulate_data"
        #   groups[1] = "2"
        #   groups[2] = "metadata.station_name"

        # 检查groups长度是否足够（需要至少3个元素）
        if len(groups) < 3:
            logger.error(
                "field_access_groups_insufficient",
                expression=parsed.get("type", "unknown"),
                group_count=len(groups),
                groups=groups,
                expected_min=3
            )
            raise ParameterBindingError(
                f"绑定表达式groups数量不足，需要至少3个，实际{len(groups)}个: {groups}"
            )

        # 【修复】正确访问groups索引
        if groups[0] is not None:
            tool_name = groups[0]      # 工具名
            index_str = groups[1]      # 索引
            field_path = groups[2]     # 字段路径

            # 验证索引是数字
            if not index_str.isdigit():
                raise ParameterBindingError(
                    f"索引必须是数字，实际为: {index_str}"
                )
            index = int(index_str)

            # 查找工具结果
            tool_result = self._resolve_indexed_tool(parsed, tool_results)

            # 获取字段值
            value = tool_result.get_field(field_path)

            if value is None:
                raise ParameterBindingError(
                    f"工具 {tool_name}[{index}] 中未找到字段 {field_path}"
                )

            return value
        else:
            # 处理简单索引格式 ($N.field_path)
            # 这种情况应该由 simple_index_field_access 处理
            raise ParameterBindingError(
                f"无法解析字段访问表达式: {parsed}"
            )

    def _extract_nested_field(self, data: Any, field_path: str) -> Any:
        """
        从数据中提取嵌套字段，支持数组索引

        例如：payload.data.analyzed_stations[0].station_name
        """
        try:
            current = data
            # 按点和方括号分割路径
            parts = re.split(r'\.|\[(\d+)\]', field_path)

            logger.info(
                "extract_nested_field_start",
                field_path=field_path,
                parts=parts,
                data_type=type(data).__name__,
                is_dict=isinstance(data, dict),
                dict_keys=list(data.keys()) if isinstance(data, dict) else None
            )

            for i, part in enumerate(parts):
                if not part:  # 跳过空字符串
                    logger.info(
                        "extract_nested_field_skip_empty",
                        index=i,
                        part=part
                    )
                    continue

                logger.info(
                    "extract_nested_field_processing",
                    index=i,
                    part=part,
                    current_type=type(current).__name__,
                    current_is_none=current is None,
                    is_digit=part.isdigit()
                )

                if part.isdigit():
                    # 数组索引
                    if isinstance(current, list):
                        index = int(part)
                        logger.debug(
                            "extract_nested_field_array_index",
                            index=index,
                            list_length=len(current)
                        )
                        if 0 <= index < len(current):
                            current = current[index]
                            logger.debug(
                                "extract_nested_field_array_success",
                                index=index,
                                new_current_type=type(current).__name__
                            )
                        else:
                            logger.warning(
                                "extract_nested_field_array_out_of_range",
                                index=index,
                                list_length=len(current)
                            )
                            return None
                    else:
                        logger.warning(
                            "extract_nested_field_not_list",
                            expected_list=True,
                            actual_type=type(current).__name__
                        )
                        return None
                else:
                    # 对象字段
                    if isinstance(current, dict):
                        old_current = current
                        key_found = part in old_current
                        old_val = old_current.get(part)
                        current = old_val
                        logger.info(
                            "extract_nested_field_dict_access",
                            part=part,
                            key_found=key_found,
                            old_current_type=type(old_current).__name__,
                            old_val_type=type(old_val).__name__ if old_val is not None else None,
                            new_current_type=type(current).__name__,
                            old_val_preview=str(old_val)[:50] if old_val is not None else "None"
                        )
                    else:
                        logger.warning(
                            "extract_nested_field_not_dict",
                            expected_dict=True,
                            actual_type=type(current).__name__,
                            current_value=str(current)[:50] if current is not None else "None"
                        )
                        return None

            logger.debug(
                "extract_nested_field_success",
                field_path=field_path,
                result_type=type(current).__name__
            )
            return current
        except Exception as e:
            logger.warning(
                "nested_field_extraction_failed",
                field_path=field_path,
                error=str(e),
                exc_info=True
            )
            return None

    def _resolve_context_nested(
        self,
        parsed: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Any:
        """解析上下文嵌套访问，如: get_weather_data[0].context.lat"""
        # context格式: {tool_name: {index: ToolResult}}
        tool_name = parsed["groups"][0]
        index = int(parsed["groups"][1])
        context_field = parsed["groups"][2]

        # 从上下文中获取值
        if tool_name in context and isinstance(context[tool_name], dict):
            tool_context = context[tool_name].get(index, {})
            return tool_context.get(context_field)

        raise ParameterBindingError(
            f"上下文 {tool_name}[{index}] 中未找到字段 {context_field}"
        )

    def _resolve_wildcard(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> List[str]:
        """解析通配符引用，如: weather:*, component:*"""
        expert_prefix = parsed["groups"][0]

        # 收集匹配的工具结果
        data_ids = []
        for result in tool_results:
            if result.tool_name.startswith(expert_prefix) and result.success:
                if result.data_id:
                    data_ids.append(result.data_id)

        if not data_ids:
            raise ParameterBindingError(
                f"未找到专家 {expert_prefix} 的工具结果"
            )

        return data_ids

    def _resolve_special_value(
        self,
        parsed: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Any:
        """解析特殊值，如: {auto_generate}, {first_available}"""
        value_name = parsed["groups"][0]

        special_value_resolvers = {
            "auto_generate": self._generate_auto_value,
            "first_available": self._get_first_available,
            "all_results": self._get_all_results,
            "location": lambda ctx: ctx.get("location", ""),
            "lat": lambda ctx: ctx.get("lat"),
            "lon": lambda ctx: ctx.get("lon"),
            # PMF动态数据源选择解析器
            "auto_pmf_data_id": self._resolve_auto_pmf_data_id,
            "auto_pmf_pollutant_type": self._resolve_auto_pmf_pollutant_type,
        }

        resolver = special_value_resolvers.get(value_name)
        if resolver:
            return resolver(context)
        else:
            # 未知特殊值，返回原值
            return f"{{{value_name}}}"

    def _generate_auto_value(self, context: Dict[str, Any]) -> str:
        """【修复】自动生成查询参数值"""
        # 基于上下文自动生成合适的查询参数
        location = context.get("location", "目标区域")
        pollutants = context.get("pollutants", [])
        pollutant_str = "、".join(pollutants) if pollutants else "污染物"

        # 解析时间范围
        start_time_str = context.get("start_time", "")
        end_time_str = context.get("end_time", "")

        # 提取日期部分（去除时间）
        start_date = start_time_str.replace(" 00:00:00", "").replace(" 23:59:59", "") if start_time_str else ""
        end_date = end_time_str.replace(" 00:00:00", "").replace(" 23:59:59", "") if end_time_str else ""

        # 生成时间范围描述
        if start_date and end_date:
            if start_date == end_date:
                time_range_desc = f"{start_date}"
            else:
                time_range_desc = f"{start_date}到{end_date}"
        else:
            time_range_desc = "最近几天"

        # 根据污染物类型生成查询
        if pollutants and "O3" in pollutants:
            return f"查询{location}{time_range_desc}的臭氧污染情况，包括浓度变化和超标情况"
        elif pollutants and any(p in pollutants for p in ["PM2.5", "PM10"]):
            return f"查询{location}{time_range_desc}的颗粒物污染情况，包括PM2.5和PM10浓度"
        elif pollutants:
            return f"查询{location}{time_range_desc}的{', '.join(pollutants)}污染情况"
        else:
            return f"查询{location}{time_range_desc}的空气质量数据，包括各项污染物指标"

    def _get_first_available(self, context: Dict[str, Any]) -> Optional[str]:
        """【修复】获取第一个可用的data_id"""
        # 从上下文中查找第一个data_id
        logger.info(
            "searching_first_available_data_id",
            context_keys=list(context.keys()),
            context_sample={k: (str(v)[:50] if len(str(v)) > 50 else v) for k, v in list(context.items())[:5]}
        )

        # 优先从可用data_ids列表中获取（更可靠的方式）
        available_ids = context.get("available_ids", [])
        if available_ids and isinstance(available_ids, list):
            first_id = available_ids[0]
            logger.info(
                "found_first_available_from_list",
                data_id=first_id,
                total_available=len(available_ids)
            )
            return first_id

        # 备用方式：从上下文中查找第一个data_id
        for key, value in context.items():
            if isinstance(value, str) and value.startswith("data_id:"):
                logger.info(
                    "found_first_available_from_context",
                    data_id=value,
                    context_key=key
                )
                return value

        # 如果没找到，尝试从工具结果中查找
        tool_results = context.get("tool_results", [])
        if tool_results:
            for result in tool_results:
                if isinstance(result, dict):
                    data_id = result.get("data_id")
                    if data_id:
                        logger.info(
                            "found_first_available_from_tool_results",
                            data_id=data_id,
                            tool_name=result.get("tool", "unknown")
                        )
                        return data_id

        logger.warning("no_first_available_data_id_found")
        return None

    def _get_all_results(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """获取所有结果"""
        # 返回上下文中的所有结果
        return context

    def _resolve_auto_pmf_data_id(self, context: Dict[str, Any]) -> Optional[str]:
        """
        【新增】自动解析PMF数据ID

        优先级：
        1. 优先使用VOCs数据（data_id以vocs:v开头，支持vocs:v1:hash格式）
        2. 其次使用颗粒物数据（data_id以particulate:v开头，支持particulate:v1:hash格式）
        3. 如果都不可用，返回None
        """
        tool_results = context.get("tool_results", [])

        # 收集VOCs和颗粒物数据
        vocs_data_id = None
        particulate_data_id = None

        for result in tool_results:
            data_id = None

            # 兼容处理：ToolResult对象或字典格式
            if hasattr(result, 'data_id'):
                # ToolResult对象
                data_id = result.data_id
            elif isinstance(result, dict):
                # 字典格式
                data_id = result.get("data_id") or result.get("metadata", {}).get("data_id", "")
            else:
                continue

            if not data_id:
                continue

            # 【修复】data_id格式为 schema:v1:hash，需要检查前缀
            # 支持格式：vocs:v1:xxx, vocs_unified:v1:xxx, particulate:v1:xxx, particulate_unified:v1:xxx 等
            if data_id.startswith("vocs:") or data_id.startswith("vocs_unified:"):
                vocs_data_id = data_id
            elif data_id.startswith("particulate:") or data_id.startswith("particulate_unified:"):
                particulate_data_id = data_id

        # 优先返回VOCs数据ID
        if vocs_data_id:
            logger.info(
                "auto_pmf_selected_vocs_data_id",
                data_id=vocs_data_id,
                reason="VOCs data available, prioritizing for source apportionment"
            )
            return vocs_data_id

        # 如果VOCs不可用，返回颗粒物数据ID
        if particulate_data_id:
            logger.info(
                "auto_pmf_selected_particulate_data_id",
                data_id=particulate_data_id,
                reason="VOCs data not available, using particulate data for PM source apportionment"
            )
            return particulate_data_id

        logger.warning("auto_pmf_no_data_id_available")
        return None

    def _resolve_auto_pmf_pollutant_type(self, context: Dict[str, Any]) -> str:
        """
        【新增】自动解析PMF污染物类型

        优先级：
        1. 如果有VOCs数据，返回VOCs
        2. 如果有颗粒物数据，根据 pollutants 上下文确定（PM2.5或PM10）
        3. 默认返回PM2.5
        """
        tool_results = context.get("tool_results", [])
        pollutants = context.get("pollutants", [])

        # 检查是否有VOCs数据
        for result in tool_results:
            data_id = None

            # 兼容处理：ToolResult对象或字典格式
            if hasattr(result, 'data_id'):
                # ToolResult对象
                data_id = result.data_id
            elif isinstance(result, dict):
                # 字典格式
                data_id = result.get("data_id") or result.get("metadata", {}).get("data_id", "")
            else:
                continue

            # 【修复】同时检查 particulate_unified 格式
            if data_id and (data_id.startswith("vocs:") or data_id.startswith("vocs_unified:")):
                logger.info(
                    "auto_pmf_pollutant_type_vocs",
                    reason="VOCs data available for source apportionment"
                )
                return "VOCs"

        # 根据上下文确定PM类型
        if "PM2.5" in pollutants:
            logger.info(
                "auto_pmf_pollutant_type_pm25",
                reason="PM2.5 in pollutants context"
            )
            return "PM2.5"
        elif "PM10" in pollutants:
            logger.info(
                "auto_pmf_pollutant_type_pm10",
                reason="PM10 in pollutants context"
            )
            return "PM10"

        # 默认返回PM2.5
        logger.info(
            "auto_pmf_pollutant_type_default_pm25",
            reason="No specific PM pollutant in context, defaulting to PM2.5"
        )
        return "PM2.5"

    def _resolve_first_matching_tool(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> ToolResult:
        """
        解析第一个匹配的工具结果（解决动态索引问题）

        例如：get_component_data[FIRST] 返回最近一个成功的get_component_data工具结果
        """
        tool_name = parsed["groups"][0]

        # 反向遍历，找到最近一个成功的工具
        for result in reversed(tool_results):
            if result.tool_name == tool_name and result.success:
                logger.debug(
                    "found_first_matching_tool",
                    tool=tool_name,
                    index=result.index,
                    data_id=result.data_id
                )
                return result

        raise ParameterBindingError(
            f"未找到工具 {tool_name} 的成功执行结果"
        )

    def _resolve_first_matching_field(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> Any:
        """
        解析第一个匹配工具的字段访问（解决动态索引问题）

        例如：get_component_data[FIRST].data_id 返回最近一个成功的get_component_data的data_id
        """
        tool_name = parsed["groups"][0]
        field_path = parsed["groups"][1]

        # 查找匹配的工具结果
        tool_result = self._resolve_first_matching_tool(parsed, tool_results)

        # 获取字段值
        value = tool_result.get_field(field_path)

        if value is None:
            raise ParameterBindingError(
                f"工具 {tool_name}[FIRST] 中未找到字段 {field_path}"
            )

        logger.debug(
            "first_matching_field_accessed",
            tool=tool_name,
            field=field_path,
            value=str(value)[:100]
        )

        return value

    def _resolve_fallback_field(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult],
        context: Dict[str, Any]
    ) -> Any:
        """
        解析带fallback的字段访问

        例如：get_component_data[FIRST].metadata.station_name or {location}
        - 优先尝试获取第一个表达式的值
        - 如果获取不到或为空，使用第二个表达式（fallback）的值
        """
        primary_expr = parsed["groups"][0].strip()
        fallback_expr = parsed["groups"][1].strip()

        logger.debug(
            "fallback_field_resolving",
            primary=primary_expr,
            fallback=fallback_expr
        )

        # 【修复】创建 enriched_context，包含 tool_results 以便特殊值解析器可以访问
        enriched_context = dict(context)
        enriched_context["tool_results"] = tool_results

        # 尝试解析主表达式
        value = None
        try:
            # 如果主表达式包含工具调用，尝试解析
            if "[" in primary_expr and "]" in primary_expr:
                # 这是一个工具字段访问表达式
                primary_parsed = self._parse_binding_expression(primary_expr)

                # 尝试不同的解析策略
                if primary_parsed["type"] == "first_matching_field":
                    value = self._resolve_first_matching_field(primary_parsed, tool_results)
                elif primary_parsed["type"] == "field_access":
                    value = self._resolve_field_access(primary_parsed, tool_results)
                elif primary_parsed["type"] == "context_field":
                    value = context.get(primary_parsed["groups"][0])
                elif primary_parsed["type"] == "special_value":
                    # 【修复】使用 enriched_context 包含 tool_results
                    value = self._resolve_special_value(primary_parsed, enriched_context)
            else:
                # 简单字段访问
                value = context.get(primary_expr)

        except Exception as e:
            logger.debug(
                "fallback_field_primary_failed",
                primary=primary_expr,
                error=str(e)
            )
            value = None

        # 如果主表达式获取不到值，使用fallback
        # 【修复】使用 value is None 判断，支持空字符串作为有效值
        if value is None:
            logger.debug(
                "fallback_field_using_fallback",
                primary=primary_expr,
                fallback=fallback_expr
            )

            # 解析fallback表达式
            try:
                fallback_parsed = self._parse_binding_expression(fallback_expr)

                if fallback_parsed["type"] == "context_field":
                    value = context.get(fallback_parsed["groups"][0], fallback_expr)
                elif fallback_parsed["type"] == "special_value":
                    # 【修复】使用 enriched_context 包含 tool_results
                    value = self._resolve_special_value(fallback_parsed, enriched_context)
                elif fallback_parsed["type"] == "unknown":
                    # 【修复】fallback表达式不包含花括号时，尝试作为context字段名获取
                    # 例如：fallback_expr = "location" (from "get_x[FIRST].y or location")
                    if fallback_expr in context:
                        value = context[fallback_expr]
                    else:
                        value = fallback_expr  # 使用原值
                else:
                    value = fallback_expr  # 使用原值
            except Exception as e:
                logger.debug(
                    "fallback_field_fallback_failed",
                    fallback=fallback_expr,
                    error=str(e)
                )
                value = fallback_expr

        logger.debug(
            "fallback_field_resolved",
            primary=primary_expr,
            fallback=fallback_expr,
            value=str(value)[:100]
        )

        return value

    def _resolve_simple_index(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> Any:
        """
        解析简单索引引用，如: $0, $1

        这种格式表示引用按执行顺序排列的工具结果列表中的第N个结果
        返回整个工具结果（不限制字段）

        例如：
        - $0 返回第一个工具的完整结果
        - $1 返回第二个工具的完整结果

        常用于工具只需要上游结果的完整数据而不需要特定字段的场景
        """
        index = int(parsed["groups"][0])

        logger.debug(
            "resolving_simple_index",
            index=index,
            total_results=len(tool_results)
        )

        # 检查索引是否在有效范围内
        if index < 0 or index >= len(tool_results):
            raise ParameterBindingError(
                f"索引 {index} 超出范围，有效范围: 0-{len(tool_results)-1}"
            )

        # 获取指定索引的工具结果
        tool_result = tool_results[index]

        logger.debug(
            "simple_index_resolved",
            index=index,
            tool_name=tool_result.tool_name,
            tool_index=tool_result.index,
            success=tool_result.success
        )

        # 返回完整的工具结果（字典格式）
        # 这是关键：简单的$N表达式返回整个结果对象，而非特定字段
        return tool_result.result

    def _resolve_simple_index_field_access(
        self,
        parsed: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> Any:
        """
        解析简单索引字段访问，如: $2.payload.data.analyzed_stations[0]

        这种格式表示引用按执行顺序排列的工具结果列表中的第N个结果的特定字段
        返回指定字段的值（支持嵌套路径和数组索引）

        例如：
        - $2.payload.data.analyzed_stations[0] 返回第三个工具结果的analyzed_stations数组的第一个元素
        """
        groups = parsed["groups"]
        index = int(groups[0])  # 索引数字
        field_path = groups[1]  # 完整字段路径

        logger.info(
            "resolve_simple_index_field_access_start",
            index=index,
            field_path=field_path,
            total_results=len(tool_results),
            tool_names=[r.tool_name for r in tool_results]
        )

        # 检查索引是否在有效范围内
        if index < 0 or index >= len(tool_results):
            logger.error(
                "simple_index_out_of_range",
                index=index,
                valid_range=f"0-{len(tool_results)-1}"
            )
            raise ParameterBindingError(
                f"索引 {index} 超出范围，有效范围: 0-{len(tool_results)-1}"
            )

        # 获取指定索引的工具结果
        tool_result = tool_results[index]

        logger.info(
            "simple_index_field_access_target",
            index=index,
            tool_name=tool_result.tool_name,
            tool_index=tool_result.index,
            success=tool_result.success,
            result_keys=list(tool_result.result.keys()) if isinstance(tool_result.result, dict) else "N/A"
        )

        # 解析字段路径（可能包含数组索引）
        value = self._extract_nested_field(tool_result.result, field_path)

        logger.info(
            "simple_index_field_access_result",
            index=index,
            field_path=field_path,
            value_type=type(value).__name__,
            value_is_none=value is None,
            value_preview=str(value)[:100] if value is not None else "None"
        )

        return value

    def collect_tool_results(
        self,
        tool_executions: List[Dict[str, Any]]
    ) -> List[ToolResult]:
        """收集工具执行结果"""
        results = []

        for i, execution in enumerate(tool_executions):
            tool_name = execution.get("tool", f"tool_{i}")
            result_data = execution.get("result", {})
            index = execution.get("index", i)

            result = ToolResult(
                tool_name=tool_name,
                index=index,
                result=result_data
            )
            results.append(result)

        return results

    def validate_binding(
        self,
        tool_name: str,
        input_bindings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        验证绑定配置是否有效

        Args:
            tool_name: 工具名称
            input_bindings: 输入绑定配置

        Returns:
            验证结果
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        # 检查工具是否存在
        tool_exists = False
        for expert_name, expert_config in self.dependency_graphs.items():
            if "tools" in expert_config and tool_name in expert_config["tools"]:
                tool_exists = True
                break

        if not tool_exists:
            validation_result["warnings"].append(
                f"工具 {tool_name} 未在依赖图中定义"
            )

        # 检查绑定表达式
        for param_name, binding_expr in input_bindings.items():
            parsed = self._parse_binding_expression(binding_expr)

            if parsed["type"] == "unknown":
                validation_result["warnings"].append(
                    f"参数 {param_name} 使用了未知的绑定表达式: {binding_expr}"
                )

        return validation_result

    def explain_binding(
        self,
        tool_name: str,
        param_name: str,
        binding_expr: str,
        context: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> str:
        """
        解释绑定过程（用于调试）

        Args:
            tool_name: 工具名称
            param_name: 参数名称
            binding_expr: 绑定表达式
            context: 执行上下文
            tool_results: 工具结果

        Returns:
            绑定解释字符串
        """
        try:
            parsed = self._parse_binding_expression(binding_expr)

            explanation = [
                f"参数: {param_name}",
                f"表达式: {binding_expr}",
                f"类型: {parsed['type']}",
                f"描述: {parsed['description']}"
            ]

            # 添加具体值信息
            bound_value = self.bind_parameters(
                tool_name,
                {param_name: binding_expr},
                context,
                tool_results
            ).get(param_name)

            if bound_value is not None:
                explanation.append(f"绑定值: {str(bound_value)[:100]}")
            else:
                explanation.append("绑定值: None (可能绑定失败)")

            return " | ".join(explanation)

        except Exception as e:
            return f"参数: {param_name} | 表达式: {binding_expr} | 错误: {str(e)}"


def create_parameter_binder() -> ParameterBinder:
    """创建参数绑定器实例"""
    return ParameterBinder()
