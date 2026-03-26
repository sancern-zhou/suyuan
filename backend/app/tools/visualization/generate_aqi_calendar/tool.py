"""
AQI日历图生成工具

通过data_id生成AQI日历热力图，支持单城市和多城市展示。

功能：
- 支持单城市和多城市（最多21个）展示
- 支持AQI及6项污染物指标（SO2、NO2、CO、O3_8h、PM2.5、PM10）
- 根据国家空气质量标准渲染颜色
- 直接返回图片URL，无需前端开发
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.services.image_cache import get_image_cache

logger = structlog.get_logger()

# 广东省21个城市
GUANGDONG_CITIES = [
    '广州', '深圳', '珠海', '汕头', '佛山', '韶关', '湛江', '肇庆',
    '江门', '茂名', '惠州', '梅州', '汕尾', '河源', '阳江', '清远',
    '东莞', '中山', '潮州', '揭阳', '云浮'
]

# 支持的污染物指标
SUPPORTED_POLLUTANTS = ['AQI', 'SO2', 'NO2', 'CO', 'O3_8h', 'PM2_5', 'PM10']

# 污染物字段映射
POLLUTANT_FIELD_MAP = {
    'AQI': 'aqi',
    'SO2': 'so2',
    'NO2': 'no2',
    'CO': 'co',
    'O3_8h': 'o3_8h',
    'PM2_5': 'pm2_5',
    'PM10': 'pm10'
}


class GenerateAQICalendarTool(LLMTool):
    """AQI日历图生成工具"""

    def __init__(self):
        super().__init__(
            name="generate_aqi_calendar",
            description=(
                "生成AQI日历热力图，支持单城市和多城市展示。"
                "通过data_id获取数据，生成包含日期和AQI/污染物浓度的日历图，"
                "颜色根据国家空气质量标准自动渲染。"
                "支持指标：AQI、SO2、NO2、CO、O3_8h、PM2.5、PM10。"
                "返回图片URL和统计信息。"
            ),
            category=ToolCategory.VISUALIZATION,
            version="1.0.0",
            requires_context=False
        )

    def get_parameter_schema(self) -> Dict[str, Any]:
        """获取参数schema"""
        return {
            "type": "object",
            "properties": {
                "data_id": {
                    "type": "string",
                    "description": "数据ID（来自query_new_standard_report等查询工具的返回结果）"
                },
                "year": {
                    "type": "integer",
                    "description": "年份（如2026）"
                },
                "month": {
                    "type": "integer",
                    "description": "月份（1-12）"
                },
                "pollutant": {
                    "type": "string",
                    "description": "污染物指标",
                    "enum": SUPPORTED_POLLUTANTS,
                    "default": "AQI"
                },
                "cities": {
                    "type": "array",
                    "description": "城市列表（可选，默认为广东省21个城市）",
                    "items": {
                        "type": "string"
                    },
                    "default": GUANGDONG_CITIES
                }
            },
            "required": ["data_id", "year", "month"]
        }

    async def execute(
        self,
        data_id: str,
        year: int,
        month: int,
        pollutant: str = "AQI",
        cities: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具

        Args:
            data_id: 数据ID
            year: 年份
            month: 月份
            pollutant: 污染物指标（默认AQI）
            cities: 城市列表（可选）

        Returns:
            {
                "success": True,
                "data": {
                    "image_url": "/api/image/xxx",
                    "markdown_image": "![AQI日历](/api/image/xxx)",
                    "statistics": {...}
                },
                "summary": "..."
            }
        """
        try:
            # 参数验证
            self._validate_parameters(data_id, year, month, pollutant, cities)

            # 默认使用广东省21个城市
            if cities is None:
                cities = GUANGDONG_CITIES

            # 限制城市数量
            if len(cities) > 21:
                cities = cities[:21]

            # 导入渲染器（延迟导入，避免循环依赖）
            from .calendar_renderer import AQICalendarRenderer, calculate_iaqi
            import json
            from pathlib import Path

            # 读取数据（直接读取文件，避免data_registry.load_dataset的bug）
            try:
                # 解析data_id，格式：schema:v1:hash
                parts = data_id.split(":")
                if len(parts) < 3:
                    raise ValueError(f"无效的data_id格式：{data_id}")

                # 构建文件路径
                safe_id = f"{parts[0]}_v1_{parts[2]}"
                data_file = Path("backend_data_registry/datasets") / f"{safe_id}.json"

                if not data_file.exists():
                    # 尝试使用相对路径
                    from app.services.data_registry import data_registry
                    data_file = data_registry.datasets_dir / f"{safe_id}.json"

                if not data_file.exists():
                    raise ValueError(f"数据文件不存在：{data_file}")

                # 直接读取JSON文件
                with data_file.open("r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                # raw_data应该是一个列表（JSON数组）
                if not isinstance(raw_data, list):
                    # 如果是字典，尝试提取records字段
                    if isinstance(raw_data, dict) and "records" in raw_data:
                        raw_data = raw_data["records"]
                    else:
                        raise ValueError(f"不支持的数据格式：期望列表或包含records的字典，实际得到{type(raw_data)}")

            except Exception as e:
                raise ValueError(f"数据ID {data_id} 不存在或无法加载：{str(e)}")

            if not raw_data:
                raise ValueError(f"数据ID {data_id} 不存在或无数据")

            # 处理数据：按城市分组，构建日期→值映射
            city_data_map = self._process_city_data(
                raw_data, cities, year, month, pollutant
            )

            # 调试：检查城市数据
            logger.info(
                "city_data_map_prepared",
                total_cities=len(city_data_map),
                city_names=list(city_data_map.keys()),
                sample_data={k: len(v) for k, v in list(city_data_map.items())[:3]}
            )

            # 计算统计信息
            statistics = self._calculate_statistics(city_data_map, year, month)

            # 渲染日历图
            renderer = AQICalendarRenderer()
            image_base64 = renderer.render_calendar(
                city_data_map, year, month, pollutant
            )

            # 保存图片
            cache = get_image_cache()
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            chart_id = f"aqi_calendar_{year}_{month}_{pollutant}_{timestamp}"
            saved_info = cache.save(image_base64, chart_id)

            # 构建返回结果
            image_url = saved_info['url']

            # 使用 HTML 标签显示下标（避免下划线被 markdownItKatex 误解析）
            if pollutant == 'O3_8h':
                display_pollutant = 'O<sub>3</sub> 8h'
            elif pollutant == 'PM2_5':
                display_pollutant = 'PM2.5'
            elif pollutant == 'SO2':
                display_pollutant = 'SO<sub>2</sub>'
            elif pollutant == 'NO2':
                display_pollutant = 'NO<sub>2</sub>'
            else:
                display_pollutant = pollutant

            markdown_image = f"![{year}年{month}月{display_pollutant}日历]({image_url})"

            return {
                "success": True,
                "data": {
                    "image_url": image_url,
                    "markdown_image": markdown_image,
                    "statistics": statistics
                },
                "summary": (
                    f"已生成{year}年{month}月{display_pollutant}日历图，"
                    f"包含{len(cities)}个城市，"
                    f"数据覆盖率{statistics['coverage_rate']}%，"
                    f"平均值{statistics.get('avg_value', 'N/A')}，"
                    f"范围{statistics.get('min_value', 'N/A')}-{statistics.get('max_value', 'N/A')}。"
                    f"**图片链接**（请在FINAL_ANSWER中使用）：{markdown_image}"
                )
            }

        except Exception as e:
            logger.error("generate_aqi_calendar_failed",
                        data_id=data_id,
                        year=year,
                        month=month,
                        pollutant=pollutant,
                        error=str(e))
            return {
                "success": False,
                "data": None,
                "summary": f"生成AQI日历图失败：{str(e)}"
            }

    def _validate_parameters(
        self,
        data_id: str,
        year: int,
        month: int,
        pollutant: str,
        cities: Optional[List[str]]
    ) -> None:
        """验证参数

        Raises:
            ValueError: 参数无效
        """
        if not data_id or not isinstance(data_id, str):
            raise ValueError("data_id必须是非空字符串")

        if not isinstance(year, int) or year < 2000 or year > 2100:
            raise ValueError("year必须是2000-2100之间的整数")

        if not isinstance(month, int) or month < 1 or month > 12:
            raise ValueError("month必须是1-12之间的整数")

        if pollutant not in SUPPORTED_POLLUTANTS:
            raise ValueError(f"pollutant必须是以下之一：{', '.join(SUPPORTED_POLLUTANTS)}")

        if cities is not None:
            if not isinstance(cities, list):
                raise ValueError("cities必须是列表")
            if len(cities) == 0:
                raise ValueError("cities列表不能为空")
            if len(cities) > 21:
                raise ValueError("最多支持21个城市")

    def _process_city_data(
        self,
        raw_data: List[Dict[str, Any]],
        cities: List[str],
        year: int,
        month: int,
        pollutant: str
    ) -> Dict[str, Dict[int, int]]:
        """处理数据：按城市分组，构建日期→值映射

        Args:
            raw_data: 原始数据列表
            cities: 城市列表
            year: 年份
            month: 月份
            pollutant: 污染物指标

        Returns:
            {city_name: {day: aqi_value}} 字典
        """
        from .calendar_renderer import calculate_iaqi

        city_data_map = {}

        # 初始化城市数据
        for city in cities:
            city_data_map[city] = {}

        # 处理每条数据
        for record in raw_data:
            # 提取城市名（支持多种字段名）
            city = record.get('city') or record.get('city_name') or record.get('station_name')
            if not city:
                continue

            # 只处理指定的城市
            if city not in cities:
                continue

            # 提取日期（支持多种字段名）
            date_str = record.get('date') or record.get('time') or record.get('timestamp')
            if not date_str:
                continue

            try:
                # 解析日期（支持多种格式）
                if isinstance(date_str, str):
                    if len(date_str) == 10:  # YYYY-MM-DD
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    elif len(date_str) == 19:  # YYYY-MM-DD HH:MM:SS
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    else:
                        continue
                else:
                    continue

                # 检查年份和月份
                if date_obj.year != year or date_obj.month != month:
                    continue

                day = date_obj.day

                # 提取污染物浓度（支持多种数据结构）
                # 1. 优先从 measurements 字段获取（新标准格式）
                # 2. 其次从顶层获取（旧格式）
                # 3. 最后从 species_data 获取IAQI（如果存在）
                concentration = None
                value = None

                # 尝试从 measurements 获取
                measurements = record.get('measurements', {})
                if measurements and isinstance(measurements, dict):
                    # 污染物名称映射（大小写兼容）
                    pollutant_key = pollutant if pollutant in measurements else pollutant.lower()
                    concentration = measurements.get(pollutant_key)

                # 如果 measurements 中没有，尝试从顶层获取
                if concentration is None:
                    field_name = POLLUTANT_FIELD_MAP.get(pollutant, pollutant.lower())
                    concentration = record.get(field_name)

                # 处理AQI（直接使用）或污染物（计算IAQI）
                if pollutant == 'AQI':
                    # 尝试多种AQI字段
                    if concentration is not None:
                        value = concentration
                    else:
                        # 尝试从 species_data 获取 IAQI_SO2 等，但这不是总AQI
                        # 暂时跳过
                        pass
                else:
                    if concentration is None or concentration <= 0:
                        continue
                    # 计算IAQI
                    value = calculate_iaqi(float(concentration), pollutant)

                # 存储数据
                if value is not None and value >= 0:
                    city_data_map[city][day] = int(value)

            except (ValueError, TypeError) as e:
                logger.warning("date_parse_failed", date_str=date_str, error=str(e))
                continue

        return city_data_map

    def _calculate_statistics(
        self,
        city_data_map: Dict[str, Dict[int, int]],
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """计算统计信息

        Args:
            city_data_map: 城市数据映射
            year: 年份
            month: 月份

        Returns:
            统计信息字典
        """
        import calendar

        days_in_month = calendar.monthrange(year, month)[1]
        city_count = len(city_data_map)

        # 计算总数据点和覆盖率
        total_days = city_count * days_in_month
        covered_days = sum(len(daily_map) for daily_map in city_data_map.values())
        coverage_rate = f"{covered_days / total_days * 100:.1f}%" if total_days > 0 else "0%"

        # 收集所有有效值
        all_values = []
        for daily_map in city_data_map.values():
            all_values.extend(daily_map.values())

        # 计算统计值
        if all_values:
            avg_value = sum(all_values) / len(all_values)
            max_value = max(all_values)
            min_value = min(all_values)
        else:
            avg_value = 0
            max_value = 0
            min_value = 0

        return {
            "city_count": city_count,
            "days_in_month": days_in_month,
            "covered_days": covered_days,
            "coverage_rate": coverage_rate,
            "avg_value": f"{avg_value:.1f}",
            "max_value": max_value,
            "min_value": min_value
        }
