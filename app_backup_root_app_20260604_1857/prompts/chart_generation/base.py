"""
BaseChartPrompt - 图表Prompt抽象基类

每个图表类型继承此类，提供专用的prompt模板。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import json


class BaseChartPrompt(ABC):
    """
    图表Prompt基类

    每个图表类型继承此类，提供专用的prompt模板
    """

    @property
    @abstractmethod
    def chart_type(self) -> str:
        """图表类型标识"""
        pass

    @abstractmethod
    def build_prompt(
        self,
        data: Dict[str, Any],
        title: Optional[str],
        **kwargs
    ) -> str:
        """
        构建完整prompt

        Args:
            data: 数据样本
            title: 图表标题
            **kwargs: 其他参数

        Returns:
            完整的prompt字符串
        """
        pass

    def get_base_context(self) -> str:
        """获取基础上下文（所有图表通用）"""
        return """
你是一个高级数据可视化专家。请分析数据并生成Chart v3.1标准格式的图表配置。

# Chart v3.1 核心规范

## 必需字段
- id: 唯一标识符（字符串）
- type: 图表类型（枚举值）
- title: 图表标题（字符串）
- data: 图表数据（根据type不同，结构不同）
- meta: 元数据（对象）

## Meta字段（必填）
- schema_version: "3.1"
- generator: "llm_generated"
- unit: 数据单位（如果适用）
- station_name: 站点名称（如果适用）
- pollutant: 污染物类型（如果适用）

# 重要规则
1. 所有数值必须是number类型，不能是string
2. 只返回JSON，不要markdown代码块
3. 确保data结构符合对应图表类型的规范
        """.strip()

    def get_examples(self) -> str:
        """
        获取示例（子类可覆盖）
        """
        return ""

    def format_data_sample(
        self,
        data: Any,
        max_length: int = 3000
    ) -> str:
        """
        格式化数据样本

        Args:
            data: 原始数据
            max_length: 最大长度（字符数）

        Returns:
            格式化的JSON字符串
        """
        data_json = json.dumps(data, ensure_ascii=False, indent=2)
        if len(data_json) > max_length:
            return data_json[:max_length] + "\n... (数据已截断)"
        return data_json
