"""
工具Schema动态注入机制

当LLM连续调用工具出错时，自动注入工具的完整schema到上下文中
"""

from typing import Dict, Any, List, Optional
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)


class SchemaInjector:
    """
    Schema注入器

    职责：
    1. 跟踪工具调用错误
    2. 检测连续错误模式
    3. 自动注入工具schema
    """

    def __init__(self, consecutive_error_threshold: int = 2):
        """
        初始化Schema注入器

        Args:
            consecutive_error_threshold: 连续错误阈值，达到此值时触发schema注入
        """
        self.consecutive_error_threshold = consecutive_error_threshold
        self.tool_error_counts: defaultdict[str, int] = defaultdict(int)
        self.injected_schemas: set = set()  # 已注入的schema（避免重复）

    def record_tool_result(self, tool_name: str, observation: Dict[str, Any]) -> None:
        """
        记录工具执行结果

        Args:
            tool_name: 工具名称
            observation: 工具执行结果
        """
        success = observation.get("success", False)
        error_type = observation.get("error_type")

        # 只记录参数验证失败（可以注入schema解决）
        if not success and error_type in ["INPUT_VALIDATION_FAILED", "TOOL_EXECUTION_FAILED"]:
            self.tool_error_counts[tool_name] += 1

            logger.warning(
                "tool_error_recorded",
                tool_name=tool_name,
                error_count=self.tool_error_counts[tool_name],
                error_type=error_type,
                error=observation.get("error", "")[:100]
            )
        else:
            # 成功或非参数错误，重置计数
            if self.tool_error_counts[tool_name] > 0:
                logger.info(
                    "tool_error_count_reset",
                    tool_name=tool_name,
                    previous_count=self.tool_error_counts[tool_name]
                )
            self.tool_error_counts[tool_name] = 0

    def should_inject_schema(self, tool_name: str) -> bool:
        """
        判断是否应该注入工具schema

        Args:
            tool_name: 工具名称

        Returns:
            是否应该注入
        """
        error_count = self.tool_error_counts.get(tool_name, 0)

        # 达到阈值且未注入过
        should_inject = (
            error_count >= self.consecutive_error_threshold
            and tool_name not in self.injected_schemas
        )

        if should_inject:
            logger.info(
                "schema_injection_triggered",
                tool_name=tool_name,
                error_count=error_count,
                threshold=self.consecutive_error_threshold
            )

        return should_inject

    def get_tool_schema(self, tool_name: str, tool_registry: Dict) -> Optional[str]:
        """
        获取工具的完整schema（用于注入）

        Args:
            tool_name: 工具名称
            tool_registry: 工具注册表

        Returns:
            Schema文本或None
        """
        try:
            tool_func = tool_registry.get(tool_name)
            if not tool_func:
                return None

            # 尝试从工具对象获取schema
            if hasattr(tool_func, 'schema'):
                # 如果工具有schema属性
                schema = tool_func.schema
            elif hasattr(tool_func, '_build_schema'):
                # 如果工具有_build_schema方法
                schema = tool_func._build_schema()
            elif hasattr(tool_func, '__self__') and hasattr(tool_func.__self__, '_build_schema'):
                # 如果是绑定方法
                schema = tool_func.__self__._build_schema()
            else:
                return None

            # 格式化schema为可读文本
            schema_text = self._format_schema(tool_name, schema)
            self.injected_schemas.add(tool_name)

            return schema_text

        except Exception as e:
            logger.error(
                "failed_to_get_tool_schema",
                tool_name=tool_name,
                error=str(e)
            )
            return None

    def _format_schema(self, tool_name: str, schema: Dict[str, Any]) -> str:
        """
        格式化schema为可读文本

        Args:
            tool_name: 工具名称
            schema: Schema字典

        Returns:
            格式化的schema文本
        """
        lines = [
            f"\n## 📋 工具Schema: {tool_name}\n",
            f"**描述**: {schema.get('description', '无描述')}\n",
            "**参数**:\n"
        ]

        properties = schema.get('properties', {})
        required = schema.get('required', [])

        for param_name, param_info in properties.items():
            param_type = param_info.get('type', 'unknown')
            param_desc = param_info.get('description', '')
            is_required = param_name in required

            # 构建参数描述
            param_line = f"- `{param_name}` ({param_type}"

            # 添加enum约束
            if 'enum' in param_info:
                enum_values = param_info['enum']
                param_line += f", enum: {enum_values}"

            # 添加数值约束
            if 'minimum' in param_info or 'maximum' in param_info:
                min_val = param_info.get('minimum')
                max_val = param_info.get('maximum')
                range_str = f"{min_val}-{max_val}" if min_val and max_val else f">={min_val}" if min_val else f"<={max_val}"
                param_line += f", range: {range_str}"

            param_line += ")"

            # 标记必需参数
            if is_required:
                param_line += " **[必需]**"

            param_line += f": {param_desc}"
            lines.append(param_line)

            # 添加默认值
            if 'default' in param_info:
                default_val = param_info['default']
                lines.append(f"  - 默认值: `{default_val}`")

        lines.append("\n**示例调用**:")
        lines.append(f"```json")
        lines.append(f"{{")
        lines.append(f"  \"tool\": \"{tool_name}\",")

        # 构造示例
        example_args = []
        for param_name in required[:3]:  # 最多3个必需参数
            param_info = properties.get(param_name, {})
            param_type = param_info.get('type', 'string')
            example_val = '"示例值"' if param_type == 'string' else '示例值'
            example_args.append(f'    "{param_name}": {example_val}')

        if example_args:
            lines.append(f"  \"args\": {{")
            lines.append(",\n".join(example_args))
            lines.append(f"  }}")
        else:
            lines.append(f"  \"args\": {{}}")

        lines.append(f"}}")
        lines.append(f"```\n")

        return "\n".join(lines)

    def reset(self) -> None:
        """重置所有状态（用于新会话）"""
        self.tool_error_counts.clear()
        self.injected_schemas.clear()
        logger.debug("schema_injector_reset")

    def get_error_summary(self) -> Dict[str, int]:
        """
        获取错误统计摘要

        Returns:
            工具错误计数字典
        """
        return dict(self.tool_error_counts)
