"""
快速溯源执行器 (QuickTraceExecutor)

专门用于污染高值告警场景的快速溯源分析

工具链:
1. get_current_weather - 当天实时气象数据
2. get_weather_data - 历史气象数据(前3天)
3. get_weather_forecast - 未来15天预报
4. _get_air_quality_from_db - 从数据库获取空气质量(周边8市历史+未来7天预报)
5. meteorological_trajectory_analysis - 后向轨迹分析(可跳过)
6. get_weather_situation_map - 中央气象台天气形势图AI解读(通义千问VL)

总耗时: 3-5分钟 (轨迹分析超时则2-3分钟)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
import structlog
import asyncio
import time
import uuid
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class SimpleExecutionContext:
    """简化的执行上下文，用于工具调用"""

    def __init__(self):
        self.session_id = f"quick_trace_{uuid.uuid4().hex[:12]}"
        self.iteration = 1

    async def save_data(self, data, schema, metadata=None):
        """空实现，仅返回一个假的data_id"""
        return f"quick_trace_{schema}:{uuid.uuid4().hex[:8]}"

    def get_data(self, data_id):
        """空实现"""
        return None

    @property
    def data_manager(self):
        """兼容性属性 - 返回自身"""
        return self


class QuickTraceExecutor:
    """快速溯源执行器"""

    # 城市经纬度映射 (目前仅支持济宁)
    CITY_COORDINATES = {
        "济宁市": {"lat": 35.4154, "lon": 116.5875}
    }

    # 周边城市列表 (固定顺序，按地理方位)
    NEARBY_CITIES = [
        "菏泽市", "枣庄市", "临沂市",
        "泰安市", "徐州市", "商丘市", "开封市"
    ]

    def __init__(self):
        """初始化执行器"""
        # 加载工具
        self._load_tools()
        logger.info(
            "quick_trace_executor_initialized",
            tools=list(self.tools.keys())
        )

    def _load_tools(self):
        """加载所需工具"""
        self.tools = {}

        # 1. 历史气象工具 (ERA5)
        try:
            from app.tools.query.get_weather_data.tool import GetWeatherDataTool
            self.tools["weather_data"] = GetWeatherDataTool()
            logger.info("工具加载成功: weather_data")
        except ImportError as e:
            logger.error("工具加载失败: weather_data", error=str(e))

        # 2. 天气预报工具 (包含今天00:00~当前时刻完整数据，包含边界层高度)
        try:
            from app.tools.query.get_weather_forecast.tool import GetWeatherForecastTool
            self.tools["weather_forecast"] = GetWeatherForecastTool()
            logger.info("工具加载成功: weather_forecast")
        except ImportError as e:
            logger.error("工具加载失败: weather_forecast", error=str(e))

        # 3. 轨迹分析工具
        try:
            from app.tools.analysis.meteorological_trajectory_analysis.tool import MeteorologicalTrajectoryAnalysisTool
            self.tools["trajectory_analysis"] = MeteorologicalTrajectoryAnalysisTool()
            logger.info("工具加载成功: trajectory_analysis")
        except ImportError as e:
            logger.error("工具加载失败: trajectory_analysis", error=str(e))

        # 4. 天气形势图解读工具
        try:
            from app.tools.query.get_weather_situation_map.tool import GetWeatherSituationMapTool
            self.tools["weather_situation_map"] = GetWeatherSituationMapTool()
            logger.info("工具加载成功: weather_situation_map")
        except ImportError as e:
            logger.error("工具加载失败: weather_situation_map", error=str(e))

    async def execute(
        self,
        city: str,
        alert_time: str,
        pollutant: str,
        alert_value: float
    ) -> Dict[str, Any]:
        """
        执行快速溯源分析

        Args:
            city: 城市名称 (如 "济宁市")
            alert_time: 告警时间 (如 "2026-02-02 12:00:00")
            pollutant: 污染物类型 (如 "PM2.5")
            alert_value: 告警浓度值

        Returns:
            Dict: 分析结果
                {
                    "summary_text": "Markdown报告",
                    "visuals": [],
                    "confidence": 0.85,
                    "data_ids": [],
                    "has_trajectory": False,
                    "warning_message": None
                }
        """
        start_time = time.time()

        # 1. 参数解析
        coords = self._parse_coordinates(city)
        if not coords:
            return self._error_result(f"不支持的城市: {city}")

        alert_dt = datetime.strptime(alert_time, "%Y-%m-%d %H:%M:%S")

        logger.info(
            "quick_trace_execute_start",
            city=city,
            lat=coords["lat"],
            lon=coords["lon"],
            alert_time=alert_time,
            pollutant=pollutant,
            alert_value=alert_value
        )

        # 2. 执行工具链 (并行执行)
        results = {}
        data_ids = []
        warning_message = None
        has_trajectory = False

        # 计算历史气象查询时间范围
        start_time_hist = alert_dt - timedelta(days=3)
        end_time_hist = alert_dt - timedelta(days=1)

        # 创建简化的执行上下文
        context = SimpleExecutionContext()

        try:
            # 所有工具完全独立，并行执行
            logger.info("executing_all_tools_in_parallel")

            # 定义所有任务（移除current_weather，数据已包含在forecast中）
            tasks = {
                "historical_weather": self.tools["weather_data"].execute(
                    context=context,  # 简化的context
                    data_type="era5",  # 使用ERA5数据
                    lat=coords["lat"],
                    lon=coords["lon"],
                    start_time=start_time_hist.strftime("%Y-%m-%d %H:%M:%S"),
                    end_time=end_time_hist.strftime("%Y-%m-%d %H:%M:%S")
                ),
                "forecast": self.tools["weather_forecast"].execute(
                    context=context,  # 添加必需的context参数
                    lat=coords["lat"],
                    lon=coords["lon"],
                    location_name=city,
                    forecast_days=15,  # 延长至15天预报
                    past_days=1,  # 获取昨天+今天00:00~当前时刻完整数据（包含边界层高度）
                    hourly=True,
                    daily=True
                ),
                "regional_comparison": self._get_air_quality_from_db(
                    city=city
                ),
                "trajectory": self._get_trajectory_analysis(
                    context=context,
                    lat=coords["lat"],
                    lon=coords["lon"],
                    start_time=alert_time,
                    timeout_seconds=180
                ),
                "weather_situation_map": self.tools["weather_situation_map"].execute(
                    date=alert_dt.strftime("%Y%m%d"),  # 使用告警日期
                    analysis_focus="污染扩散条件"
                )
            }

            # 并行执行所有任务
            completed_results = await self._execute_parallel(tasks)

            # 整理结果
            for tool_name, result in completed_results.items():
                results[tool_name] = result
                logger.info(
                    "tool_completed",
                    tool=tool_name,
                    success=result.get("success", False)
                )

            has_trajectory = results.get("trajectory", {}).get("success", False)
            if not has_trajectory:
                warning_message = "轨迹分析超时或失败，报告不包含轨迹分析结果"

            # 3. 生成报告
            logger.info("step_6_generate_summary")
            summary_result = await self._generate_summary(
                results=results,
                city=city,
                pollutant=pollutant,
                alert_value=alert_value,
                alert_time=alert_time
            )

            # 快速溯源场景不需要data_ids，直接使用空列表
            # data_ids主要用于数据追踪，对分析报告无影响
            data_ids = []

            return {
                "summary_text": summary_result["summary_text"],
                "visuals": summary_result.get("visuals", []),
                "data_ids": data_ids,
                "has_trajectory": has_trajectory,
                "warning_message": warning_message
            }

        except Exception as e:
            logger.error(
                "quick_trace_execute_failed",
                city=city,
                error=str(e),
                exc_info=True
            )
            return self._error_result(f"执行失败: {str(e)}")

    def _parse_coordinates(self, city: str) -> Optional[Dict[str, float]]:
        """解析城市经纬度"""
        return self.CITY_COORDINATES.get(city)

    async def _execute_parallel(
        self,
        tasks: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        并行执行多个任务

        Args:
            tasks: 任务字典 {task_name: coroutine}

        Returns:
            Dict: {task_name: result}
        """
        results = {}

        # 并行执行所有任务
        task_list = [
            self._run_single_task(name, coro)
            for name, coro in tasks.items()
        ]

        # 等待所有任务完成
        completed_tasks = await asyncio.gather(*task_list, return_exceptions=True)

        # 整理结果
        for i, (task_name, result) in enumerate(zip(tasks.keys(), completed_tasks)):
            if isinstance(result, Exception):
                logger.error(
                    "task_failed",
                    task=task_name,
                    error=str(result),
                    exc_info=result
                )
                results[task_name] = {"success": False, "error": str(result)}
            else:
                results[task_name] = result

        return results

    async def _run_single_task(
        self,
        task_name: str,
        coroutine: Any
    ) -> Any:
        """
        运行单个任务并记录日志

        Args:
            task_name: 任务名称
            coroutine: 协程对象

        Returns:
            任务执行结果
        """
        try:
            logger.info("task_started", task=task_name)
            result = await coroutine
            logger.info("task_completed", task=task_name, success=result.get("success", False))
            return result
        except Exception as e:
            logger.error(
                "task_exception",
                task=task_name,
                error=str(e),
                exc_info=True
            )
            raise

    async def _get_air_quality_from_db(
        self,
        city: str
    ) -> Dict[str, Any]:
        """
        从数据库获取空气质量数据

        包括：
        1. 未来7天日预报数据 (air_quality_forecast) - 优先calculated_aqi
        2. 周边8城市历史12小时数据 (CityAQIPublishHistory)

        Args:
            city: 城市名称

        Returns:
            Dict: 空气质量数据
        """
        from app.db.database import async_session
        from app.db.models import AirQualityForecast

        all_records = []
        summary_parts = []

        try:
            async with async_session() as session:
                # 1. 查询未来7天日预报数据（包含今天，共计7条）
                try:
                    today = date.today()
                    end_date = today + timedelta(days=6)  # 今天 + 6天 = 7天

                    forecast_query = select(AirQualityForecast).where(
                        and_(
                            AirQualityForecast.forecast_date >= today,
                            AirQualityForecast.forecast_date <= end_date,
                            AirQualityForecast.source.in_(["qweather", "waqi", "combined", "open-meteo", "sql-server"])
                        )
                    ).order_by(AirQualityForecast.forecast_date)

                    forecast_result = await session.execute(forecast_query)
                    forecast_rows = forecast_result.scalars().all()

                    for row in forecast_rows:
                        # 优先使用 calculated_aqi，否则使用 aqi
                        aqi = row.calculated_aqi if row.calculated_aqi is not None else row.aqi
                        primary_pollutant = row.calculated_primary_pollutant if row.calculated_primary_pollutant else row.primary_pollutant
                        aqi_level = row.calculated_aqi_level if row.calculated_aqi_level else row.aqi_level

                        record = {
                            "timestamp": row.forecast_date.strftime("%Y-%m-%d"),
                            "station_name": city,
                            "measurements": {
                                "AQI": aqi,
                                "primary_pollutant": primary_pollutant,
                                "quality": aqi_level
                            },
                            "metadata": {
                                "source": row.source,
                                "data_type": "forecast"
                            }
                        }

                        # 添加六参数数据 (如果有)
                        if row.pollutants:
                            pollutants = row.pollutants if isinstance(row.pollutants, dict) else {}
                            record["measurements"].update({
                                "PM2.5": pollutants.get("pm25"),
                                "PM10": pollutants.get("pm10"),
                                "O3": pollutants.get("o3"),
                                "NO2": pollutants.get("no2"),
                                "SO2": pollutants.get("so2"),
                                "CO": pollutants.get("co")
                            })

                        all_records.append(record)

                    if forecast_rows:
                        summary_parts.append(f"未来7天预报: {len(forecast_rows)}条")

                    logger.info(
                        "air_quality_forecast_retrieved",
                        city=city,
                        count=len(forecast_rows)
                    )

                except Exception as e:
                    logger.error("get_forecast_data_failed", city=city, error=str(e))

                # 2. 查询周边8城市历史12小时数据 (从SQL Server数据库)
                try:
                    history_records = await self._get_city_history_from_sqlserver(city)
                    all_records.extend(history_records)

                    if history_records:
                        summary_parts.append(f"历史12小时: {len(history_records)}条")

                    logger.info(
                        "air_quality_history_retrieved_from_sqlserver",
                        city=city,
                        nearby_cities=self.NEARBY_CITIES,
                        hours=12,
                        count=len(history_records)
                    )

                except Exception as e:
                    logger.error("get_history_data_failed_from_sqlserver", city=city, error=str(e), exc_info=True)

            # 标准化数据
            from app.utils.data_standardizer import get_data_standardizer
            standardized_records = []
            data_standardizer = get_data_standardizer()

            for record in all_records:
                standardized_measurements = {}
                for key, value in record.get("measurements", {}).items():
                    standard_key = data_standardizer._get_standard_field_name(key)
                    final_key = standard_key if standard_key else key
                    normalized_value = data_standardizer._normalize_value(value)
                    if normalized_value is not None:
                        standardized_measurements[final_key] = normalized_value

                standardized_record = {
                    "timestamp": record["timestamp"],
                    "station_name": record["station_name"],
                    "measurements": standardized_measurements,
                    "metadata": record.get("metadata", {})
                }
                standardized_records.append(standardized_record)

            summary = "; ".join(summary_parts) if summary_parts else "无数据"

            return {
                "status": "success" if standardized_records else "empty",
                "success": len(standardized_records) > 0,
                "data": standardized_records,
                "summary": f"查询{city}空气质量: {summary}"
            }

        except Exception as e:
            logger.error(
                "air_quality_db_query_failed",
                city=city,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "data": [],
                "summary": f"查询失败: {str(e)[:50]}"
            }

    async def _get_trajectory_analysis(
        self,
        context,
        lat: float,
        lon: float,
        start_time: str,
        timeout_seconds: int = 90
    ) -> Dict[str, Any]:
        """获取轨迹分析 (带超时控制)"""
        try:
            result = await asyncio.wait_for(
                self.tools["trajectory_analysis"].execute(
                    context=context,  # 使用传入的context
                    lat=lat,
                    lon=lon,
                    start_time=start_time,
                    hours=72,
                    heights=[100, 500, 1000],
                    direction="Backward"
                ),
                timeout=timeout_seconds
            )
            logger.info("trajectory_analysis_success")
            return result

        except asyncio.TimeoutError:
            logger.warning(
                "trajectory_analysis_timeout",
                timeout=timeout_seconds
            )
            return {"success": False, "error": "超时"}

        except Exception as e:
            logger.error(
                "trajectory_analysis_failed",
                error=str(e)
            )
            return {"success": False, "error": str(e)}

    async def _generate_summary(
        self,
        results: Dict[str, Any],
        city: str,
        pollutant: str,
        alert_value: float,
        alert_time: str
    ) -> Dict[str, Any]:
        """生成总结报告 (LLM)"""
        from app.services.llm_service import llm_service

        # 提取数据摘要（传递alert_time用于判断今天数据）
        summary_parts = self._extract_data_summaries(results, pollutant, alert_time)

        # 构建Prompt
        prompt = self._build_prompt(
            city=city,
            pollutant=pollutant,
            alert_value=alert_value,
            alert_time=alert_time,
            summaries=summary_parts
        )

        # 调用LLM
        try:
            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=4096
            )

            return {
                "summary_text": response.strip(),
                "visuals": []  # 快速溯源不需要可视化，直接返回空列表
            }

        except Exception as e:
            logger.error(
                "summary_generation_failed",
                error=str(e)
            )
            return {
                "summary_text": f"报告生成失败: {str(e)}",
                "visuals": []
            }

    def _extract_data_summaries(
        self,
        results: Dict[str, Any],
        pollutant: str,
        alert_time: str = None
    ) -> Dict[str, str]:
        """提取数据摘要 - 传递完整原始数据给LLM，不只是摘要"""
        summaries = {}

        # 历史气象数据 - 传递完整数据（ERA5前3天）
        historical = results.get("historical_weather", {})
        if isinstance(historical, dict) and historical.get("success"):
            summaries["historical_weather"] = self._format_weather_data(historical, "历史")

        # 预报数据 - 传递完整数据（包含昨天+今天00:00~当前时刻+未来7天）
        forecast = results.get("forecast", {})
        if isinstance(forecast, dict) and forecast.get("success"):
            summaries["forecast"] = self._format_forecast_data(forecast, alert_time)
        else:
            summaries["forecast"] = forecast.get("summary", "无数据") if isinstance(forecast, dict) else "无数据"

        # 区域对比摘要
        regional = results.get("regional_comparison", {})
        if isinstance(regional, dict):
            summaries["regional"] = self._format_regional_summary(regional, pollutant)

        # 轨迹摘要 + 图片URL
        trajectory = results.get("trajectory", {})
        if isinstance(trajectory, dict):
            summaries["trajectory"] = trajectory.get("summary", "轨迹分析失败")

            # 提取轨迹图片URL（如果存在）
            if trajectory.get("success") and trajectory.get("visuals"):
                visuals = trajectory.get("visuals", [])
                if visuals and len(visuals) > 0:
                    visual = visuals[0]  # 第一个visual是轨迹图
                    # 从payload或meta中获取相对路径URL
                    image_url = visual.get("payload", {}).get("image_url") or visual.get("meta", {}).get("image_url")
                    if image_url:
                        # 保存相对路径，让LLM在prompt中拼接完整域名
                        summaries["trajectory_image_url"] = image_url
                        logger.info("trajectory_image_url_extracted", relative_url=image_url)

        # 天气形势图解读
        weather_situation = results.get("weather_situation_map", {})
        if isinstance(weather_situation, dict):
            if weather_situation.get("success"):
                data = weather_situation.get("data", {})
                summaries["weather_situation"] = data.get("analysis", "天气形势图解读失败")
                summaries["weather_situation_image_url"] = data.get("image_url", "")
                logger.info("weather_situation_extracted", has_image_url=bool(data.get("image_url")))
            else:
                summaries["weather_situation"] = weather_situation.get("summary", "天气形势图获取失败")

        return summaries

    def _format_regional_summary(
        self,
        regional_data: Dict,
        pollutant: str
    ) -> str:
        """格式化区域对比数据 - 传递完整原始数据给LLM进行分析"""
        if not regional_data.get("success"):
            return "周边城市数据查询失败"

        data_list = regional_data.get("data", [])
        if not data_list:
            return "周边城市无数据"

        # 使用DataStandardizer获取标准字段名
        from app.utils.data_standardizer import get_data_standardizer
        standardizer = get_data_standardizer()

        # 获取标准字段名（例如："PM2.5" -> "PM2_5"）
        standard_field = standardizer._get_standard_field_name(pollutant)

        lines = [f"## 空气质量数据 (完整原始数据)", f""]

        # 1. 按数据类型分组
        forecast_data = []
        history_data = []

        for record in data_list:
            if isinstance(record, dict):
                data_type = record.get("metadata", {}).get("data_type", "")
                if data_type == "forecast":
                    forecast_data.append(record)
                elif data_type == "history":
                    history_data.append(record)

        # 2. 输出未来7天预报数据
        if forecast_data:
            lines.append("### 未来7天预报数据")
            for record in forecast_data:
                timestamp = record.get("timestamp", "")
                station_name = record.get("station_name", "")
                measurements = record.get("measurements", {})
                source = record.get("metadata", {}).get("source", "")

                # 构建测量值字符串
                measurement_parts = []
                for key, value in measurements.items():
                    if value is not None and key != "primary_pollutant":
                        measurement_parts.append(f"{key}={value}")

                measurement_str = ", ".join(measurement_parts) if measurement_parts else "无"

                lines.append(f"- {timestamp} | {station_name} | {measurement_str} | 来源:{source}")
            lines.append("")

        # 3. 输出历史12小时数据（按城市分组，传递完整数据）
        if history_data:
            lines.append("### 历史前12小时监测数据 (完整每小时数据)")

            # 按城市分组
            city_records = {}
            for record in history_data:
                city_name = record.get("station_name", "未知")
                if city_name not in city_records:
                    city_records[city_name] = []
                city_records[city_name].append(record)

            # 输出每个城市的完整数据
            for city_name in sorted(city_records.keys()):
                lines.append(f"\n#### {city_name}")
                city_records[city_name].sort(key=lambda x: x.get("timestamp", ""))

                for record in city_records[city_name]:
                    timestamp = record.get("timestamp", "")
                    measurements = record.get("measurements", {})

                    # 构建完整的六参数+AQI字符串
                    all_params = []
                    param_order = ["AQI", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO"]
                    for param in param_order:
                        value = measurements.get(param)
                        if value is not None:
                            all_params.append(f"{param}={value}")

                    # 添加首要污染物和空气质量等级
                    if measurements.get("primary_pollutant"):
                        all_params.append(f"首要污染物={measurements['primary_pollutant']}")
                    if measurements.get("quality"):
                        all_params.append(f"等级={measurements['quality']}")

                    param_str = ", ".join(all_params)
                    lines.append(f"  {timestamp}: {param_str}")

            lines.append("")

        # 4. 添加统计摘要（辅助理解）
        lines.append("### 数据统计摘要")
        lines.append(f"- 预报数据: {len(forecast_data)} 条")
        lines.append(f"- 历史数据: {len(history_data)} 条")

        # 统计每个城市的数据条数
        city_counts = {}
        for record in history_data:
            city_name = record.get("station_name", "未知")
            city_counts[city_name] = city_counts.get(city_name, 0) + 1

        if city_counts:
            lines.append("- 各城市历史数据条数:")
            for city_name, count in sorted(city_counts.items()):
                lines.append(f"  - {city_name}: {count} 条")

        # 5. 针对目标污染物的特别说明
        if standard_field:
            lines.append(f"\n### 目标污染物: {pollutant} (标准字段名: {standard_field})")

            # 统计目标污染物的浓度范围
            pollutant_values = []
            for record in history_data:
                measurements = record.get("measurements", {})
                value = measurements.get(standard_field)
                if value is not None:
                    pollutant_values.append(value)

            if pollutant_values:
                lines.append(f"- 浓度范围: {min(pollutant_values):.1f} - {max(pollutant_values):.1f} μg/m³")
                lines.append(f"- 平均浓度: {sum(pollutant_values)/len(pollutant_values):.1f} μg/m³")
                lines.append(f"- 数据点数: {len(pollutant_values)}")

        return "\n".join(lines)

    def _build_prompt(
        self,
        city: str,
        pollutant: str,
        alert_value: float,
        alert_time: str,
        summaries: Dict[str, str]
    ) -> str:
        """构建LLM Prompt"""

        # 生成新的prompt模板
        new_prompt = f"""你是大气环境溯源分析专家，请基于以下监测数据生成污染溯源分析报告。

【基本情况】
城市: {city}
时间: {alert_time}
污染物: {pollutant}
浓度: {alert_value} μg/m³

【数据说明】
气象数据包含多个来源，请注意：
1. ERA5历史数据：前3天（D-3 ~ D-1）
2. Open-Meteo预报数据：昨天 + 今天00:00~当前 + 未来15天
3. 昨天数据在两个数据源中重复，但来源不同（ERA5再分析 vs Open-Meteo分析场），可交叉验证
4. 今天数据：从00:00到当前时刻的完整小时数据（Open-Meteo分析场，包含边界层高度）

【完整数据】
{summaries.get('historical_weather', '无数据')}

{summaries.get('forecast', '无数据')}

{summaries.get('regional', '无数据')}

{summaries.get('trajectory', '轨迹分析失败或超时')}

{summaries.get('weather_situation', '')}

"""
        # 如果有轨迹图片URL，添加到prompt中
        trajectory_image_section = ""
        if summaries.get('trajectory_image_url'):
            trajectory_image_section = f"""
【轨迹分析图片】
相对路径URL: {summaries['trajectory_image_url']}
服务器域名: http://219.135.180.51:56041

**重要**: 请在报告的"二、污染来源详细分析"章节末尾插入此图片。
使用Markdown格式，将服务器域名与相对路径拼接为完整URL：
![HYSPLIT后向轨迹分析](http://219.135.180.51:56041{summaries['trajectory_image_url']})
"""

        # 如果有天气形势图URL，添加到prompt中
        weather_situation_image_section = ""
        if summaries.get('weather_situation_image_url'):
            weather_situation_image_section = f"""
【天气形势图】
图片URL: {summaries['weather_situation_image_url']}

**重要**: 请在报告的"三、气象条件影响详细评估"章节末尾插入此图片。
使用Markdown格式：
![中央气象台天气形势图]({summaries['weather_situation_image_url']})
"""

        new_prompt += trajectory_image_section + weather_situation_image_section + """
---

【报告撰写要求】

请按照以下框架生成分析报告，使用流畅的段落式表述，避免过度条目化：

# {city}污染溯源分析报告

**污染物**: {pollutant} 
**生成时间**: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}

---

## 一、综合结论

[本节置于报告开头，概括本次污染过程的核心判断和关键结论，便于快速了解整体情况]

首先明确污染来源方向，基于后向轨迹分析指出主要源区和传输贡献强度（强/中/弱）。

然后判断气象条件影响，说明当前大气扩散能力（强/中/弱）及是否为静稳天气，评估气象条件对污染积累的促进作用。**重点分析今天00:00到当前时刻的边界层高度和风速变化趋势**。

接着评估区域传输作用，基于周边城市浓度数据判断本地污染是局地生成主导还是区域传输主导。

最后指出污染好转的关键时间节点，说明未来几天何时扩散条件将明显改善。

---

## 二、污染来源详细分析

[本节详细论述污染物的来源区域和传输路径]

首先描述后向轨迹分析结果，包括主要传输方向、传输距离、不同高度层的轨迹特征。分析不同高度层的轨迹差异，说明近地面层、边界层和自由对流层的传输特征。

然后结合主导风向和上风向城市浓度数据，评估区域传输贡献。列出上风向1-3个主要城市的浓度水平，并与本地浓度对比，判断是否存在明显的输入性污染。

---

## 三、气象条件影响详细评估

[本节详细分析当前气象条件对污染形成和扩散的影响]

**关键分析点**：利用今天00:00~当前时刻的完整小时数据，分析边界层高度和风速的日变化规律。

首先评估大气扩散能力。根据边界层高度（PBLH）判断垂直扩散条件，结合风速评估水平输送能力，综合给出扩散能力评价（强/中/弱）。**分析今天凌晨边界层是否持续偏低导致污染累积**。

然后分析气象要素对污染的影响。说明温度对化学反应的作用、湿度对二次生成的影响、降水的清除作用（如有）。判断当前是否为静稳天气（低边界层、小风速）。

最后总结气象条件的总体影响，指出是否存在不利扩散条件。**基于今天完整数据判断污染是从何时开始积累的**。

---

## 四、周边城市污染态势分析

[本节基于周边城市浓度数据，详细分析区域污染分布特征]

首先概述本地浓度水平（{alert_value} μg/m³）。

然后分析周边城市过去12小时的浓度变化趋势。重点描述上风向城市的浓度状况，包括浓度范围、变化趋势。对比上风向城市与本地浓度，评估区域污染的输运关系。

最后给出区域污染特征的判断，说明本地污染是局地生成主导还是区域传输主导。

---

## 五、未来趋势与好转时机

[本节基于未来7天天气预报和空气质量预报，详细预测污染变化趋势和好转时间]

首先概述未来7天边界层高度、风场、降水的演变趋势。给出扩散条件的阶段性变化特征（如"前3天持续不利，第4天起逐步改善"）。

然后明确指出污染好转的关键时间节点。具体说明哪个时间点之后扩散条件将明显改善，包括边界层高度升至多少米以上、风速增至多少米每秒以上，以及降水清除作用（如有）。

最后提供预测依据，引用具体的预报数据支撑判断。

---

## 六、空气质量预报准确性校验

[本节基于气象条件预报与空气质量预报的一致性，评估预报结果的可靠性]

首先分析扩散条件预报与空气质量预报趋势的一致性。检查边界层高度、风速等气象要素的变化趋势与预报的空气质量变化是否匹配。

然后评估降水清除效应与预报的一致性。如有降水过程，判断预报的降水时间和量级是否足以清除污染物，以及与空气质量下降预报的吻合程度。

最后给出综合判断，说明空气质量预报结果可靠、基本可靠还是存在矛盾，并指出可能导致偏差的因素。

---

## 七、其他关键发现

[本节由LLM根据输入的所有监测数据，自主归纳总结其他重要结论或异常情况]

基于提供的完整监测数据（包括气象数据、轨迹分析、周边城市浓度、预报数据等），分析是否存在其他值得关注的异常情况、特殊规律或潜在问题。例如：某些时段的浓度异常波动、特定气象条件下的污染特征、区域传输的特殊路径等。

**报告结束**

---

【撰写要点】
1. 使用段落式表述，多用连接词，保持行文流畅
2. 定量数据与定性分析相结合，避免空洞描述
3. 各章节内容要有区分，避免重复表述
4. 数据缺失时明确说明，不编造信息
5. 使用政府公文常用表达，专业规范
6. 时间格式统一为"月日时:分"或"X月X日X时"
7. 不要前后矛盾，上下文要逻辑统一
"""

        return new_prompt

    def _extract_visuals(self, results: Dict[str, Any]) -> List[Dict]:
        """提取可视化图表"""
        visuals = []

        # 轨迹图
        trajectory = results.get("trajectory", {})
        if isinstance(trajectory, dict) and trajectory.get("visuals"):
            trajectory_visuals = trajectory.get("visuals", [])
            if isinstance(trajectory_visuals, list):
                visuals.extend(trajectory_visuals)

        return visuals

    def _format_weather_data(self, weather_result: Dict, data_type: str) -> str:
        """格式化气象数据为文本 - 传递完整数据给LLM"""
        if not weather_result.get("data") or not isinstance(weather_result["data"], list):
            return weather_result.get("summary", "无数据")

        records = weather_result["data"]
        if not records:
            return weather_result.get("summary", "无数据")

        lines = [f"## {data_type}气象数据 (共{len(records)}条记录)"]

        # 按天分组显示 (每天显示3个关键时点: 00时, 12时, 23时)
        from collections import defaultdict
        daily_data = defaultdict(list)

        for record in records:
            if isinstance(record, dict):
                ts = record.get("timestamp")
                if ts:
                    # 提取日期
                    if isinstance(ts, str):
                        date_str = ts[:10]
                    else:
                        date_str = str(ts)[:10]
                    daily_data[date_str].append(record)

        # 对每天的数据，选择代表性时点
        for date in sorted(daily_data.keys())[:7]:  # 最多显示7天
            day_records = sorted(daily_data[date], key=lambda x: str(x.get("timestamp", "")))

            # 选择早中晚三个时点
            selected_points = []
            if len(day_records) >= 3:
                selected_points = [day_records[0], day_records[len(day_records)//2], day_records[-1]]
            else:
                selected_points = day_records

            lines.append(f"\n### {date}")
            for i, rec in enumerate(selected_points):
                if isinstance(rec, dict):
                    ts = rec.get("timestamp")
                    meas = rec.get("measurements", {})

                    # ERA5字段名: temperature_2m, relative_humidity_2m, wind_speed_10m, etc.
                    temp = meas.get("temperature_2m")
                    rh = meas.get("relative_humidity_2m")
                    ws = meas.get("wind_speed_10m")
                    wd = meas.get("wind_direction_10m")
                    pblh = meas.get("boundary_layer_height")
                    prec = meas.get("precipitation")

                    # 修复边界层None值格式化
                    pblh_str = f"{pblh}m" if pblh is not None else "无数据"

                    time_str = str(ts)[11:19] if ts else "未知"
                    lines.append(f"- {time_str}: 温度{temp}°C, 湿度{rh}%, 风速{ws}m/s, 风向{wd}°, 边界层{pblh_str}, 降水{prec}mm")

        return "\n".join(lines)

    def _format_forecast_data(self, forecast_result: Dict, alert_time: str = None) -> str:
        """
        格式化预报数据为文本 - 传递完整数据给LLM

        数据说明：
        - 包含昨天、今天、未来7天的完整数据
        - 昨天数据与ERA5历史数据有重复，但数据来源不同（Open-Meteo分析场 vs ERA5再分析）
        - 今天数据: 00:00 ~ 当前时刻（分析场数据，包含边界层高度）
        - 未来数据: 未来7天预报

        Args:
            forecast_result: 预报数据结果
            alert_time: 告警时间，用于判断"今天"和截取今天00:00~当前时刻的数据
        """
        if not forecast_result.get("data") or not isinstance(forecast_result["data"], list):
            return forecast_result.get("summary", "无数据")

        records = forecast_result["data"]
        if not records:
            return forecast_result.get("summary", "无数据")

        from collections import defaultdict
        from datetime import datetime

        # 按天分组
        daily_data = defaultdict(list)
        for record in records:
            if isinstance(record, dict):
                ts = record.get("timestamp")
                if ts:
                    if isinstance(ts, str):
                        date_str = ts[:10]
                    else:
                        date_str = str(ts)[:10]
                    daily_data[date_str].append(record)

        # 解析告警时间，判断"今天"
        alert_date_str = None
        alert_hour = None
        if alert_time:
            try:
                alert_dt = datetime.strptime(alert_time, "%Y-%m-%d %H:%M:%S")
                alert_date_str = alert_dt.strftime("%Y-%m-%d")
                alert_hour = alert_dt.hour
            except Exception as e:
                logger.warning("failed_to_parse_alert_time", alert_time=alert_time, error=str(e))

        lines = [f"## 完整气象数据 (共{len(records)}个小时数据点)"]
        lines.append("(数据来源: Open-Meteo Forecast API，包含昨天分析场、今天分析场、未来预报)")
        lines.append("(注: 昨天数据与ERA5历史数据有重叠，但数据源不同，可交叉验证)")

        # 输出所有天数据（昨天、今天、未来）
        for date in sorted(daily_data.keys()):
            day_records = sorted(daily_data[date], key=lambda x: str(x.get("timestamp", "")))

            # 识别日期类型（基于alert_time判断）
            if alert_date_str:
                if date < alert_date_str:
                    date_label = f"{date} (告警前，历史分析场数据)"
                elif date == alert_date_str:
                    alert_time_str = f"{alert_hour:02d}:00" if alert_hour is not None else "当前"
                    date_label = f"{date} (告警当天，从00:00到{alert_time_str}，分析场数据)"
                else:
                    date_label = f"{date} (未来，预报数据)"
            else:
                # 降级：使用datetime.now()判断
                today = datetime.now().strftime("%Y-%m-%d")
                if date < today:
                    date_label = f"{date} (昨天及以前，分析场数据)"
                elif date == today:
                    date_label = f"{date} (今天，分析场数据)"
                else:
                    date_label = f"{date} (未来，预报数据)"

            lines.append(f"\n### {date_label}")

            # 选择数据点
            if alert_date_str and date == alert_date_str and alert_hour is not None:
                # ✅ 告警当天：传递从00:00到告警时刻的完整小时数据
                selected_points = []
                for rec in day_records:
                    ts = rec.get("timestamp")
                    if ts:
                        ts_str = str(ts)
                        if len(ts_str) > 13:
                            try:
                                hour = int(ts_str[11:13])
                                if hour <= alert_hour:
                                    selected_points.append(rec)
                            except (ValueError, IndexError):
                                selected_points.append(rec)
                logger.info(f"selected_today_data_points", date=date, alert_hour=alert_hour, count=len(selected_points))
            else:
                # 其他天：采样3个关键时点控制数据量
                if len(day_records) >= 3:
                    selected_points = [day_records[0], day_records[len(day_records)//2], day_records[-1]]
                else:
                    selected_points = day_records

            for rec in selected_points:
                if isinstance(rec, dict):
                    ts = rec.get("timestamp")
                    meas = rec.get("measurements", {})

                    # 使用标准化字段名
                    temp = meas.get("temperature") or meas.get("temperature_2m")
                    rh = meas.get("humidity") or meas.get("relative_humidity_2m")
                    ws = meas.get("wind_speed") or meas.get("wind_speed_10m")
                    wd = meas.get("wind_direction") or meas.get("wind_direction_10m")
                    pblh = meas.get("boundary_layer_height")
                    prec = meas.get("precipitation")
                    prec_prob = meas.get("precipitation_probability")
                    cloud = meas.get("cloud_cover")

                    # 修复边界层None值格式化
                    pblh_str = f"{pblh}m" if pblh is not None else "无数据"

                    time_str = str(ts)[11:16] if len(str(ts)) > 16 else str(ts)

                    if alert_date_str and date >= alert_date_str:
                        # 告警当天及未来：显示降水概率
                        lines.append(f"- {time_str}: 温度{temp}°C, 湿度{rh}%, 风速{ws}m/s, 风向{wd}°, 边界层{pblh_str}, 降水{prec}mm (概率{prec_prob}%), 云量{cloud}%")
                    else:
                        # 告警前：不显示降水概率
                        lines.append(f"- {time_str}: 温度{temp}°C, 湿度{rh}%, 风速{ws}m/s, 风向{wd}°, 边界层{pblh_str}, 降水{prec}mm, 云量{cloud}%")

        return "\n".join(lines)

    async def _get_city_history_from_sqlserver(
        self,
        city: str
    ) -> List[Dict[str, Any]]:
        """
        从SQL Server数据库查询周边城市历史12小时空气质量数据

        数据库: XcAiDb @ 180.184.30.94:1433
        表名: CityAQIPublishHistory

        Args:
            city: 城市名称

        Returns:
            List[Dict]: 历史空气质量数据列表
        """
        import pyodbc
        import os
        from datetime import datetime, timedelta

        records = []
        cities = [city] + self.NEARBY_CITIES

        # SQL Server 连接配置
        sql_server_config = {
            'driver': '{ODBC Driver 17 for SQL Server}',
            'server': '180.184.30.94',
            'port': 1433,
            'database': 'XcAiDb',
            'uid': 'sa',
            'pwd': '#Ph981,6J2bOkWYT7p?5slH$I~g_0itR'
        }

        conn = None
        cursor = None

        try:
            # 构建连接字符串
            conn_str = (
                f"DRIVER={sql_server_config['driver']};"
                f"SERVER={sql_server_config['server']},{sql_server_config['port']};"
                f"DATABASE={sql_server_config['database']};"
                f"UID={sql_server_config['uid']};"
                f"PWD={sql_server_config['pwd']};"
                f"TrustServerCertificate=yes;"
            )

            # 连接数据库
            conn = pyodbc.connect(conn_str, timeout=10)
            cursor = conn.cursor()

            # 计算时间范围 (前12小时)
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=12)

            # 构建SQL查询
            # CityAQIPublishHistory表字段: TimePoint, Area, CityCode, CO, NO2, O3, PM10, PM2_5, SO2, AQI, PrimaryPollutant, Quality, CreateTime, Id
            city_placeholders = ','.join(['?' for _ in cities])

            sql_query = f"""
                SELECT
                    TimePoint, Area, CityCode,
                    CO, NO2, O3, PM10, PM2_5, SO2,
                    AQI, PrimaryPollutant, Quality
                FROM CityAQIPublishHistory WITH (NOLOCK)
                WHERE Area IN ({city_placeholders})
                    AND TimePoint >= ?
                    AND TimePoint <= ?
                ORDER BY TimePoint DESC
            """

            # 执行查询
            params = cities + [start_time, end_time]
            cursor.execute(sql_query, params)

            # 获取列名
            columns = [column[0] for column in cursor.description]

            # 处理结果
            for row in cursor.fetchall():
                row_dict = dict(zip(columns, row))

                # 辅助函数：安全转换字符串为数值
                def safe_float(value):
                    """安全转换字符串为浮点数"""
                    if value is None or value == '':
                        return None
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return None

                def safe_int(value):
                    """安全转换字符串为整数"""
                    if value is None or value == '':
                        return None
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        return None

                record = {
                    "timestamp": row_dict['TimePoint'].strftime("%Y-%m-%d %H:%M:%S") if row_dict['TimePoint'] else "",
                    "station_name": row_dict['Area'],
                    "measurements": {
                        "CO": safe_float(row_dict.get('CO')),
                        "NO2": safe_float(row_dict.get('NO2')),
                        "O3": safe_float(row_dict.get('O3')),
                        "PM10": safe_float(row_dict.get('PM10')),
                        "PM2.5": safe_float(row_dict.get('PM2_5')),
                        "SO2": safe_float(row_dict.get('SO2')),
                        "AQI": safe_int(row_dict.get('AQI')),
                        "primary_pollutant": row_dict.get('PrimaryPollutant'),
                        "quality": row_dict.get('Quality')
                    },
                    "metadata": {
                        "source": "sqlserver_monitoring",
                        "data_type": "history",
                        "city_code": row_dict.get('CityCode')
                    }
                }
                records.append(record)

            logger.info(
                "sqlserver_city_history_query_success",
                cities=cities,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                count=len(records)
            )

            return records

        except pyodbc.Error as e:
            logger.error(
                "sqlserver_connection_error",
                error=str(e),
                error_type=type(e).__name__,
                sqlserver_host=sql_server_config['server']
            )
            return []

        except Exception as e:
            logger.error(
                "sqlserver_query_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return []

        finally:
            # 关闭连接
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _error_result(self, error_message: str) -> Dict[str, Any]:
        """返回错误结果"""
        return {
            "summary_text": f"❌ 分析失败: {error_message}",
            "visuals": [],
            "data_ids": [],
            "has_trajectory": False,
            "warning_message": error_message
        }
