"""
IAQI分指数计算工具

基于污染物浓度计算IAQI（中国环境空气质量指数）分指数。

**计算标准**:
- PM2.5: 24小时平均浓度
- PM10: 24小时平均浓度
- SO2: 24小时平均浓度
- NO2: 24小时平均浓度
- CO: 24小时平均浓度
- O3: 日最大8小时平均浓度

**等级划分**:
- 优 (0-50): 绿色
- 良 (51-100): 黄色
- 轻度污染 (101-150): 橙色
- 中度污染 (151-200): 红色
- 重度污染 (201-300): 紫色
- 严重污染 (301-500): 褐红色

**输入**:
- pollutant_data: 污染物浓度数据
- target_time: 目标时刻

**输出**:
- IAQI分指数列表
- 综合空气质量等级
- 可视化图表（雷达图显示各污染物分指数）
"""

from typing import Dict, List, Any, Optional
import asyncio
from datetime import datetime
import pandas as pd
import numpy as np
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


class IAQICalculatorTool(LLMTool):
    """IAQI分指数计算工具"""

    # IAQI标准限值表（基于GB 3095-2012）
    IAQI_STANDARDS = {
        'PM2_5': {
            'breakpoints': [0, 35, 75, 115, 150, 250, 350, 500],
            'values': [0, 50, 100, 150, 200, 300, 400, 500],
            'unit': 'ug/m3'
        },
        'PM10': {
            'breakpoints': [0, 54, 164, 254, 354, 424, 504, 604],
            'values': [0, 50, 100, 150, 200, 300, 400, 500],
            'unit': 'ug/m3'
        },
        'SO2': {
            'breakpoints': [0, 20, 60, 90, 140, 200, 400, 600],
            'values': [0, 50, 100, 150, 200, 300, 400, 500],
            'unit': 'ug/m3'
        },
        'NO2': {
            'breakpoints': [0, 40, 80, 120, 180, 280, 400, 600],
            'values': [0, 50, 100, 150, 200, 300, 400, 500],
            'unit': 'ug/m3'
        },
        'CO': {
            'breakpoints': [0, 2, 4, 14, 24, 36, 48, 60],
            'values': [0, 50, 100, 150, 200, 300, 400, 500],
            'unit': 'mg/m3'
        },
        'O3': {
            'breakpoints': [0, 100, 160, 215, 265, 800, 1000, 1200],
            'values': [0, 50, 100, 150, 200, 300, 400, 500],
            'unit': 'ug/m3'
        }
    }

    # 等级配置
    AQI_LEVELS = {
        (0, 50): {'level': 1, 'name': '优', 'color': '#00E400', 'description': '空气质量令人满意'},
        (51, 100): {'level': 2, 'name': '良', 'color': '#FFFF00', 'description': '空气质量可接受'},
        (101, 150): {'level': 3, 'name': '轻度污染', 'color': '#FF7E00', 'description': '敏感人群症状轻微加剧'},
        (151, 200): {'level': 4, 'name': '中度污染', 'color': '#FF0000', 'description': '敏感人群症状加剧'},
        (201, 300): {'level': 5, 'name': '重度污染', 'color': '#8F3F97', 'description': '心脏病和肺病患者症状显著加剧'},
        (301, 500): {'level': 6, 'name': '严重污染', 'color': '#7E0023', 'description': '健康警告，所有人都可能出现症状'}
    }

    def __init__(self):
        function_schema = {
            "name": "calculate_iaqi",
            "description": """
IAQI分指数计算

基于污染物浓度计算IAQI（中国环境空气质量指数）分指数。

**计算标准**:
- PM2.5: 24小时平均浓度
- PM10: 24小时平均浓度
- SO2: 24小时平均浓度
- NO2: 24小时平均浓度
- CO: 24小时平均浓度
- O3: 日最大8小时平均浓度

**等级划分**:
- 优 (0-50): 绿色
- 良 (51-100): 黄色
- 轻度污染 (101-150): 橙色
- 中度污染 (151-200): 红色
- 重度污染 (201-300): 紫色
- 严重污染 (301-500): 褐红色

**输入参数**:
- pollutant_data: 污染物浓度字典
  - PM2_5: PM2.5浓度 (μg/m³)
  - PM10: PM10浓度 (μg/m³)
  - SO2: SO2浓度 (μg/m³)
  - NO2: NO2浓度 (μg/m³)
  - CO: CO浓度 (mg/m³)
  - O3: O3浓度 (μg/m³)
- target_time: 目标时刻（可选，ISO 8601格式）
- station_name: 站点名称（可选）

**输出**:
- IAQI分指数列表
- 综合空气质量等级和颜色
- 雷达图可视化
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "pollutant_data": {
                        "type": "object",
                        "description": "污染物浓度数据"
                    },
                    "target_time": {
                        "type": "string",
                        "description": "目标时刻（ISO 8601格式，可选）"
                    },
                    "station_name": {
                        "type": "string",
                        "description": "站点名称（可选）"
                    }
                },
                "required": ["pollutant_data"]
            }
        }

        super().__init__(
            name="calculate_iaqi",
            description="IAQI (Individual Air Quality Index) sub-index calculation",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

    async def execute(
        self,
        pollutant_data: Dict[str, float],
        target_time: Optional[str] = None,
        station_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行IAQI计算

        Args:
            pollutant_data: 污染物浓度数据
            target_time: 目标时刻
            station_name: 站点名称

        Returns:
            IAQI计算结果
        """
        if not station_name:
            station_name = "监测站点"

        if not target_time:
            target_time = datetime.now().isoformat()

        logger.info(
            "iaqi_calculation_start",
            station_name=station_name,
            target_time=target_time,
            pollutants=list(pollutant_data.keys())
        )

        # 计算各污染物分指数
        iaqi_results = {}
        for pollutant, concentration in pollutant_data.items():
            if pollutant in self.IAQI_STANDARDS:
                iaqi_value = self._calculate_single_iaqi(pollutant, concentration)
                iaqi_results[pollutant] = {
                    'concentration': concentration,
                    'iaqi': iaqi_value,
                    'unit': self.IAQI_STANDARDS[pollutant]['unit']
                }

        # 找出最大分指数
        max_iaqi = max(result['iaqi'] for result in iaqi_results.values())
        dominant_pollutant = max(
            iaqi_results.items(),
            key=lambda x: x[1]['iaqi']
        )[0]

        # 获取空气质量等级
        aqi_level = self._get_aqi_level(max_iaqi)

        # 保存结果
        output_data = {
            'timestamp': target_time,
            'station_name': station_name,
            'iaqi_results': iaqi_results,
            'max_iaqi': max_iaqi,
            'aqi_level': aqi_level,
            'dominant_pollutant': dominant_pollutant,
            'record_count': len(iaqi_results)
        }

        # 生成可视化
        radar_chart = self._create_iaqi_radar_chart(iaqi_results, station_name, aqi_level)

        # 计算统计信息
        stats = self._calculate_statistics(iaqi_results)

        logger.info(
            "iaqi_calculation_complete",
            station_name=station_name,
            max_iaqi=max_iaqi,
            aqi_level=aqi_level['name'],
            dominant_pollutant=dominant_pollutant
        )

        return {
            "status": "success",
            "success": True,
            "data": output_data,
            "visuals": [radar_chart],
            "metadata": {
                "schema_version": "v2.0",
                "generator": "calculate_iaqi",
                "target_time": target_time,
                "station_name": station_name,
                "record_count": len(iaqi_results),
                "aqi_level": aqi_level['name'],
                "max_iaqi": max_iaqi
            },
            "summary": f"✅ IAQI计算完成：{station_name}，空气质量{aqi_level['name']}（{max_iaqi:.0f}），首要污染物：{dominant_pollutant}"
        }

    def _calculate_single_iaqi(self, pollutant: str, concentration: float) -> float:
        """
        计算单个污染物的IAQI值

        Args:
            pollutant: 污染物名称
            concentration: 浓度值

        Returns:
            IAQI分指数值
        """
        if pollutant not in self.IAQI_STANDARDS:
            return 0.0

        standards = self.IAQI_STANDARDS[pollutant]
        breakpoints = standards['breakpoints']
        iaqi_values = standards['values']

        # 查找浓度所在的区间
        for i in range(len(breakpoints) - 1):
            if breakpoints[i] <= concentration <= breakpoints[i + 1]:
                # 线性插值计算IAQI
                C_low = breakpoints[i]
                C_high = breakpoints[i + 1]
                I_low = iaqi_values[i]
                I_high = iaqi_values[i + 1]

                iaqi = I_low + (I_high - I_low) * (concentration - C_low) / (C_high - C_low)
                return iaqi

        # 超出范围的处理
        if concentration > breakpoints[-1]:
            return iaqi_values[-1]
        else:
            return iaqi_values[0]

    def _get_aqi_level(self, iaqi: float) -> Dict[str, Any]:
        """
        获取空气质量等级

        Args:
            iaqi: 最大分指数值

        Returns:
            等级信息
        """
        for (min_val, max_val), level_info in self.AQI_LEVELS.items():
            if min_val <= iaqi <= max_val:
                return level_info

        # 默认返回最高等级
        return self.AQI_LEVELS[(301, 500)]

    def _create_iaqi_radar_chart(
        self,
        iaqi_results: Dict[str, Any],
        station_name: str,
        aqi_level: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成IAQI雷达图

        Args:
            iaqi_results: IAQI计算结果
            station_name: 站点名称
            aqi_level: 空气质量等级

        Returns:
            雷达图配置
        """
        # 准备雷达图数据
        categories = []
        values = []

        pollutant_labels = {
            'PM2_5': 'PM2.5',
            'PM10': 'PM10',
            'SO2': 'SO2',
            'NO2': 'NO2',
            'CO': 'CO',
            'O3': 'O3'
        }

        for pollutant, result in iaqi_results.items():
            categories.append(pollutant_labels.get(pollutant, pollutant))
            values.append(round(result['iaqi'], 1))

        # 雷达图配置（Chart v3.1格式）
        return {
            "id": "iaqi_radar_chart",
            "type": "radar",
            "title": f"{station_name} IAQI分指数雷达图",
            "data": {
                "categories": categories,
                "series": [
                    {
                        "name": "IAQI分指数",
                        "data": values,
                        "areaStyle": {
                            "color": aqi_level['color'],
                            "opacity": 0.3
                        },
                        "lineStyle": {
                            "color": aqi_level['color'],
                            "width": 2
                        }
                    }
                ]
            },
            "meta": {
                "schema_version": "3.1",
                "generator": "calculate_iaqi",
                "scenario": "iaqi_analysis",
                "layout_hint": "wide",
                "aqi_level": aqi_level['name'],
                "aqi_color": aqi_level['color']
            }
        }

    def _calculate_statistics(self, iaqi_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算统计信息

        Args:
            iaqi_results: IAQI计算结果

        Returns:
            统计信息
        """
        if not iaqi_results:
            return {}

        iaqi_values = [result['iaqi'] for result in iaqi_results.values()]

        return {
            "average_iaqi": round(np.mean(iaqi_values), 2),
            "max_iaqi": max(iaqi_values),
            "min_iaqi": min(iaqi_values),
            "std_iaqi": round(np.std(iaqi_values), 2),
            "pollutant_count": len(iaqi_values)
        }
