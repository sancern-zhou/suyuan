"""
PromptRegistry - 提示词注册表（单例模式）

管理所有图表类型的专用prompt模板。
"""

from typing import Dict, Optional, List
from .base import BaseChartPrompt
import structlog

logger = structlog.get_logger()


class PromptRegistry:
    """
    Prompt注册表（单例）

    职责：
    - 注册和管理所有图表类型的prompt模板
    - 提供根据chart_type获取对应prompt的接口
    - 支持运行时动态注册新prompt
    """

    _instance = None
    _prompts: Dict[str, BaseChartPrompt] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """初始化注册表，注册所有内置prompt"""
        try:
            from .pie import PiePrompt
            from .bar import BarPrompt
            from .timeseries import TimeseriesPrompt
            from .wind_rose import WindRosePrompt
            from .map_chart import MapPrompt

            # 注册核心图表类型
            self._prompts = {
                "pie": PiePrompt(),
                "bar": BarPrompt(),
                "timeseries": TimeseriesPrompt(),
                "wind_rose": WindRosePrompt(),
                "map": MapPrompt(),
            }

            logger.info(
                "prompt_registry_initialized",
                registered_types=list(self._prompts.keys())
            )
        except ImportError as e:
            logger.warning(
                "prompt_registry_init_incomplete",
                error=str(e),
                message="某些prompt类未找到，将使用通用prompt"
            )

    def get_prompt(self, chart_type: str) -> Optional[BaseChartPrompt]:
        """
        获取指定类型的prompt模板

        Args:
            chart_type: 图表类型（如 "pie", "bar", "wind_rose"）

        Returns:
            对应的prompt模板，如果不存在返回None
        """
        prompt = self._prompts.get(chart_type)
        if prompt:
            logger.debug("prompt_retrieved", chart_type=chart_type)
        else:
            logger.debug("prompt_not_found", chart_type=chart_type)
        return prompt

    def register(self, chart_type: str, prompt: BaseChartPrompt):
        """
        注册新的prompt模板

        Args:
            chart_type: 图表类型
            prompt: prompt模板实例
        """
        if chart_type in self._prompts:
            logger.warning(
                "prompt_override",
                chart_type=chart_type,
                action="覆盖现有prompt"
            )

        self._prompts[chart_type] = prompt
        logger.info("prompt_registered", chart_type=chart_type)

    def unregister(self, chart_type: str) -> bool:
        """
        注销prompt模板

        Args:
            chart_type: 要注销的图表类型

        Returns:
            是否成功注销
        """
        if chart_type in self._prompts:
            del self._prompts[chart_type]
            logger.info(
                "prompt_unregistered",
                chart_type=chart_type,
                remaining_prompts=len(self._prompts)
            )
            return True
        else:
            logger.warning("prompt_not_found_for_unregister", chart_type=chart_type)
            return False

    def list_chart_types(self) -> List[str]:
        """列出所有已注册的图表类型"""
        return list(self._prompts.keys())

    def list_prompts_detailed(self) -> Dict[str, Dict[str, str]]:
        """
        列出所有prompt的详细信息

        Returns:
            图表类型到详细信息的映射
        """
        prompts_info = {}
        for chart_type, prompt in self._prompts.items():
            prompts_info[chart_type] = {
                "chart_type": chart_type,
                "class_name": prompt.__class__.__name__,
                "has_examples": bool(prompt.get_examples())
            }
        return prompts_info


# 全局单例实例
_global_prompt_registry: Optional[PromptRegistry] = None


def get_prompt_registry() -> PromptRegistry:
    """获取全局prompt注册表（单例）"""
    global _global_prompt_registry

    if _global_prompt_registry is None:
        _global_prompt_registry = PromptRegistry()

    return _global_prompt_registry
