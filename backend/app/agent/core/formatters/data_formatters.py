"""
数据工具格式化器

处理数据查询和分析工具的结果格式化。
"""

from typing import Dict, Any, List
import json

from .base import ObservationFormatter


class DataQueryFormatter(ObservationFormatter):
    """数据查询工具格式化器（列表格式）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        # 数据查询工具返回列表格式的data字段
        # 但不包含results字段（那是search_history工具）
        # 不通过generator判断，而是通过数据类型判断
        return False  # 这个格式化器由_format_observation直接调用，不通过注册表

    @classmethod
    def format(cls, observation: Dict[str, Any]) -> List[str]:
        """格式化数据查询结果

        Args:
            observation: 完整的观察结果（包含data和metadata）

        Returns:
            格式化的字符串列表
        """
        lines = []
        data_list = observation["data"]
        metadata = observation.get("metadata", {})

        # 检查是否应用了采样
        sampling_applied = metadata.get("sampling_applied", False)
        original_count = metadata.get("original_record_count", len(data_list))
        sampled_count = len(data_list)

        if data_list:
            # 显示数据预览信息
            if sampling_applied:
                lines.append(f"**数据预览** (采样{sampled_count}条/共{original_count}条):")
                sampling_info = metadata.get("sampling_info", {})
                strategy = sampling_info.get("strategy", "unknown")
                if strategy == "head_tail_middle_sampling":
                    head = sampling_info.get("head_samples", 0)
                    middle = sampling_info.get("middle_samples", 0)
                    tail = sampling_info.get("tail_samples", 0)
                    lines.append(f"  采样策略: 头部{head}条 + 中间{middle}条 + 尾部{tail}条")
            else:
                lines.append(f"**完整数据** ({sampled_count}条):")

            # 显示数据内容（JSON格式）
            lines.append(f"```json\n{json.dumps(data_list, ensure_ascii=False, indent=2, default=str)}\n```")

            # 如果有data_id，提示可以加载完整数据
            data_id = observation.get("data_id")
            if data_id and sampling_applied:
                lines.append(f"\n💡 完整数据({original_count}条)已存储在: `{data_id}`")

        return lines


class StatisticsFormatter(ObservationFormatter):
    """统计结果格式化器（字典格式）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        # 统计结果通过数据类型判断
        # 不通过generator判断，因为很多工具都返回字典格式的data
        return False  # 这个格式化器由_format_observation直接调用，不通过注册表

    @classmethod
    def format(cls, data_dict: Dict[str, Any]) -> List[str]:
        """格式化统计结果

        Args:
            data_dict: 统计结果字典

        Returns:
            格式化的字符串列表
        """
        lines = []
        if data_dict:  # 只有非空结果才显示
            lines.append(f"**统计结果**:")
            lines.append(f"```json\n{json.dumps(data_dict, ensure_ascii=False, indent=2, default=str)}\n```")
        return lines


class DetailedResultFormatter(ObservationFormatter):
    """详细结果格式化器（result字段）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        # 详细结果通过result字段判断
        # 不通过generator判断，因为很多工具都返回result字段
        return False  # 这个格式化器由_format_observation直接调用，不通过注册表

    @classmethod
    def format(cls, result: Dict[str, Any]) -> List[str]:
        """格式化详细结果

        Args:
            result: 详细结果字典

        Returns:
            格式化的字符串列表
        """
        lines = []
        if result:  # 只有非空结果才显示
            lines.append(f"**详细结果**:")
            lines.append(f"```json\n{json.dumps(result, ensure_ascii=False, indent=2, default=str)}\n```")
        return lines
