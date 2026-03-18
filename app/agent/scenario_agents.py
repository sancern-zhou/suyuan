"""
场景化Agent工厂（示例扩展）

展示如何为气象专家模式配置扩展的工具集
"""

from enum import Enum
from typing import Optional, Dict, Any
import structlog

from .react_agent import ReActAgent
from .experts.weather_executor import WeatherExecutor
from .experts.component_executor import ComponentExecutor

logger = structlog.get_logger()

class AnalysisScenario(str, Enum):
    """分析场景枚举"""
    SOURCE_TRACING = "source_tracing"
    METEOROLOGY = "meteorology"
    METEOROLOGY_COMPREHENSIVE = "meteorology_comprehensive"  # 新增：综合气象分析
    VISUALIZATION = "visualization"
    GENERAL = "general"

class EnhancedMeteorologyAgentFactory:
    """增强版气象专家工厂"""

    @staticmethod
    def create_comprehensive_meteorology_agent() -> ReActAgent:
        """创建综合气象分析Agent（气象+空气质量+可视化）"""

        agent = ReActAgent(
            enable_multi_expert=False,  # 单专家模式
            max_iterations=20,  # 更多迭代（综合分析需要更多步骤）
            max_working_memory=30
        )

        # 标记为综合气象分析场景
        agent._scenario = AnalysisScenario.METEOROLOGY_COMPREHENSIVE

        # 自定义气象专家配置
        agent._configure_enhanced_weather_executor()

        logger.info(
            "comprehensive_meteorology_agent_created",
            max_iterations=20,
            features=[
                "气象数据查询",
                "空气质量分析",
                "组分数据分析",
                "图表可视化",
                "轨迹分析",
                "上风向企业分析"
            ]
        )

        return agent

    def _configure_enhanced_weather_executor(self):
        """配置增强版气象专家执行器"""

        # 创建增强版气象执行器
        weather_executor = EnhancedWeatherExecutor()

        # 设置到agent的执行器中（如果需要）
        # 这里主要用于演示，实际项目中可能需要修改ReActAgent的初始化逻辑

        logger.info("enhanced_weather_executor_configured")

class EnhancedWeatherExecutor(WeatherExecutor):
    """增强版气象专家执行器（展示扩展用法）"""

    def _load_tools(self) -> Dict[str, Any]:
        """加载完整工具集（气象+空气质量+可视化）"""

        # 调用父类方法获取基础工具（已扩展）
        tools = super()._load_tools()

        # 工具分类统计
        weather_tools = [k for k in tools.keys() if k in [
            "get_weather_data", "get_universal_meteorology", "get_current_weather",
            "get_weather_forecast", "get_fire_hotspots", "get_dust_data",
            "get_satellite_data", "meteorological_trajectory_analysis",
            "trajectory_simulation", "analyze_upwind_enterprises"
        ]]

        air_quality_tools = [k for k in tools.keys() if k in [
            "get_air_quality", "get_component_data", "iaqi_calculator"
        ]]

        viz_tools = [k for k in tools.keys() if k in [
            "smart_chart_generator", "generate_chart", "generate_map"
        ]]

        logger.info(
            "enhanced_weather_tools_loaded",
            weather_tools=weather_tools,
            air_quality_tools=air_quality_tools,
            viz_tools=viz_tools,
            total_tools=len(tools)
        )

        return tools

# 使用示例
"""
# 创建综合气象分析Agent
agent = EnhancedMeteorologyAgentFactory.create_comprehensive_meteorology_agent()

# 使用示例查询
queries = [
    "分析北京地区2025-11-27到2025-11-29期间的气象条件与空气质量关系",
    "北京今天的风向对PM2.5浓度有什么影响？请生成相关图表",
    "分析广州地区的气象-污染物传输路径，识别上风向污染源"
]

for query in queries:
    async for event in agent.analyze(query):
        print(f"[{event['type']}] {event['data']}")
"""
