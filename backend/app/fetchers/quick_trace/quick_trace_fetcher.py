"""
快速溯源执行器 (QuickTraceExecutor)

专门用于污染高值告警场景的快速溯源分析

工具链:
1. get_current_weather - 当天实时气象数据
2. get_weather_data - 历史气象数据(前3天)
3. get_weather_forecast - 未来15天预报
4. _get_air_quality_from_db - 从数据库获取空气质量(周边8市历史+未来7天预报)
5. meteorological_trajectory_analysis - 后向轨迹分析(可跳过)
6. get_platform_weather_image - 中央气象台风场实况图

总耗时: 3-5分钟 (轨迹分析超时则2-3分钟)

定时任务: 每天早上8:30自动生成报告
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
import structlog
import asyncio
import time
import uuid
import os
import sys
from pathlib import Path
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.fetchers.base.fetcher_interface import DataFetcher

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量（从.env文件）
def load_env_vars():
    """加载环境变量（支持多个.env文件）"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("[WARNING] python-dotenv未安装，跳过.env文件加载")
        return False

    env_files = [
        project_root / ".env",
        project_root / "backend" / ".env"
    ]

    loaded_count = 0
    for env_file in env_files:
        if env_file.exists():
            try:
                load_dotenv(env_file, override=False)
                loaded_count += 1
                print(f"[INFO] 环境变量已加载: {env_file}")
            except Exception as e:
                print(f"[WARNING] 加载环境变量失败: {env_file}, 错误: {e}")

    # 验证关键环境变量
    qwen_key = os.getenv("QWEN_VL_API_KEY")
    if qwen_key:
        print(f"[INFO] QWEN_VL_API_KEY已设置: {qwen_key[:10]}...")
    else:
        print("[WARNING] QWEN_VL_API_KEY未设置，天气形势图解读可能失败")

    # 验证LLM配置
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    print(f"[INFO] LLM_PROVIDER已设置: {llm_provider}")

    if llm_provider == "mimo":
        mimo_key = os.getenv("MIMO_API_KEY")
        if mimo_key:
            print(f"[INFO] MIMO_API_KEY已设置: {mimo_key[:10]}...")
        else:
            print("[WARNING] MIMO_API_KEY未设置")

    return loaded_count > 0

# 在导入其他模块前加载环境变量
load_env_vars()

logger = structlog.get_logger()


class SimpleExecutionContext:
    """简化的执行上下文，用于工具调用"""

    def __init__(self):
        self.session_id = f"quick_trace_{uuid.uuid4().hex[:12]}"
        self.iteration = 1

    def save_data(self, data, schema, metadata=None):
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

    POLLUTANT_SQL_FIELDS = {
        "PM2.5": "PM2_5",
        "PM10": "PM10",
        "O3": "O3",
        "NO2": "NO2",
        "SO2": "SO2",
        "CO": "CO",
    }

    POLLUTANT_THRESHOLDS = {
        "PM2.5": 75.0,
        "PM10": 150.0,
        "O3": 160.0,
        "NO2": 200.0,
        "SO2": 150.0,
        "CO": 10.0,
    }

    PRIMARY_POLLUTANT_ALIASES = {
        "PM2.5": "PM2.5",
        "PM25": "PM2.5",
        "PM2_5": "PM2.5",
        "细颗粒物": "PM2.5",
        "PM10": "PM10",
        "O3": "O3",
        "O₃": "O3",
        "臭氧": "O3",
        "NO2": "NO2",
        "NO₂": "NO2",
        "二氧化氮": "NO2",
        "SO2": "SO2",
        "SO₂": "SO2",
        "二氧化硫": "SO2",
        "CO": "CO",
        "一氧化碳": "CO",
    }

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

        # 4. 平台气象图片工具（中央气象台天气形势图等）
        try:
            from app.tools.query.get_platform_weather_image.tool import GetPlatformWeatherImageTool
            self.tools["platform_weather_image"] = GetPlatformWeatherImageTool()
            logger.info("工具加载成功: platform_weather_image")
        except ImportError as e:
            logger.error("工具加载失败: platform_weather_image", error=str(e))

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
                "forecast": self._get_weather_forecast_for_alert(
                    context=context,
                    lat=coords["lat"],
                    lon=coords["lon"],
                    location_name=city,
                    alert_dt=alert_dt
                ),
                "regional_comparison": self._get_air_quality_from_db(
                    city=city,
                    reference_time=alert_dt
                ),
                "trajectory": self._get_trajectory_analysis(
                    context=context,
                    lat=coords["lat"],
                    lon=coords["lon"],
                    start_time=alert_time,
                    timeout_seconds=180,
                    meteo_source="gfs0p25"  # 强制使用GFS数据源
                ),
                "weather_situation_map": self.tools["platform_weather_image"].execute(
                    product="hourly_wind_field",
                    date=alert_dt.strftime("%Y%m%d"),
                    time="00",
                    download=True
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

    def _safe_float(self, value: Any) -> Optional[float]:
        """安全转换为浮点数。"""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_primary_pollutant(self, value: Any) -> Optional[str]:
        """标准化首要污染物名称。"""
        if value is None:
            return None
        raw = str(value).strip()
        if not raw or raw in {"-", "--", "无", "暂无", "NA", "N/A"}:
            return None

        for separator in [",", "，", "/", "、", ";", "；"]:
            if separator in raw:
                raw = raw.split(separator)[0].strip()
                break

        normalized = raw.upper().replace(" ", "")
        normalized = normalized.replace("PM2.5", "PM25").replace("PM2_5", "PM25")

        for alias, pollutant in self.PRIMARY_POLLUTANT_ALIASES.items():
            alias_key = alias.upper().replace(" ", "")
            alias_key = alias_key.replace("PM2.5", "PM25").replace("PM2_5", "PM25")
            if normalized == alias_key or alias_key in normalized:
                return pollutant
        return None

    def _pollutant_value_from_record(
        self,
        record: Dict[str, Any],
        pollutant: str
    ) -> Optional[float]:
        """从监测记录中读取指定污染物浓度。"""
        field_name = self.POLLUTANT_SQL_FIELDS.get(pollutant)
        if not field_name:
            return None
        return self._safe_float(record.get(field_name))

    def _select_analysis_event_from_records(
        self,
        city: str,
        analysis_date: str,
        records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """从单日监测记录中选择本次分析事件。"""
        if not records:
            raise ValueError(f"{city} {analysis_date} 无监测数据，无法推断分析事件")

        best = None
        for record in records:
            time_point = record.get("TimePoint")
            if not isinstance(time_point, datetime):
                continue
            for pollutant, threshold in self.POLLUTANT_THRESHOLDS.items():
                value = self._pollutant_value_from_record(record, pollutant)
                if value is None or threshold <= 0:
                    continue
                ratio = value / threshold
                if best is None or ratio > best["ratio"]:
                    best = {
                        "record": record,
                        "time_point": time_point,
                        "pollutant": pollutant,
                        "alert_value": value,
                        "ratio": ratio,
                    }

        if best is None:
            raise ValueError(f"{city} {analysis_date} 无有效污染物浓度，无法推断分析事件")

        record = best["record"]
        return {
            "success": True,
            "city": city,
            "analysis_date": analysis_date,
            "alert_time": best["time_point"].strftime("%Y-%m-%d %H:%M:%S"),
            "pollutant": best["pollutant"],
            "alert_value": best["alert_value"],
            "aqi": self._safe_float(record.get("AQI")),
            "quality": record.get("Quality"),
            "primary_pollutant": record.get("PrimaryPollutant"),
            "selection_reason": "max_threshold_ratio",
        }

    async def infer_analysis_event_from_sqlserver(
        self,
        city: str,
        analysis_date: str
    ) -> Dict[str, Any]:
        """按分析日期从SQL Server推断实际分析污染事件。"""
        import pyodbc

        analysis_day = datetime.strptime(analysis_date, "%Y-%m-%d")
        start_time = analysis_day.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=1)

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
            conn_str = (
                f"DRIVER={sql_server_config['driver']};"
                f"SERVER={sql_server_config['server']},{sql_server_config['port']};"
                f"DATABASE={sql_server_config['database']};"
                f"UID={sql_server_config['uid']};"
                f"PWD={sql_server_config['pwd']};"
                f"TrustServerCertificate=yes;"
            )
            conn = pyodbc.connect(conn_str, timeout=10)
            cursor = conn.cursor()

            sql_query = """
                SELECT
                    TimePoint, Area, CityCode,
                    CO, NO2, O3, PM10, PM2_5, SO2,
                    AQI, PrimaryPollutant, Quality
                FROM CityAQIPublishHistory WITH (NOLOCK)
                WHERE Area = ?
                    AND TimePoint >= ?
                    AND TimePoint < ?
                ORDER BY TimePoint ASC
            """
            cursor.execute(sql_query, [city, start_time, end_time])
            columns = [column[0] for column in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]

            event = self._select_analysis_event_from_records(city, analysis_date, records)
            logger.info(
                "analysis_event_inferred",
                city=city,
                analysis_date=analysis_date,
                alert_time=event["alert_time"],
                pollutant=event["pollutant"],
                alert_value=event["alert_value"],
                selection_reason=event["selection_reason"],
                record_count=len(records)
            )
            return event

        except Exception as e:
            logger.error(
                "analysis_event_inference_failed",
                city=city,
                analysis_date=analysis_date,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "city": city,
                "analysis_date": analysis_date,
                "error": str(e),
            }

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    async def execute_for_analysis_date(
        self,
        city: str,
        analysis_date: str
    ) -> Dict[str, Any]:
        """仅按分析日期执行快速溯源，自动推断污染物、浓度和告警时间。"""
        event = await self.infer_analysis_event_from_sqlserver(city, analysis_date)
        if not event.get("success"):
            return self._error_result(event.get("error", "无法推断分析事件"))

        result = await self.execute(
            city=city,
            alert_time=event["alert_time"],
            pollutant=event["pollutant"],
            alert_value=event["alert_value"],
        )
        result["inferred_event"] = event
        return result

    def _air_quality_forecast_window(
        self,
        reference_time: Optional[datetime] = None
    ) -> tuple[date, date]:
        """返回空气质量预报查询日期窗口。"""
        start_date = reference_time.date() if reference_time else date.today()
        end_date = start_date + timedelta(days=6)
        return start_date, end_date

    def _history_time_window(
        self,
        reference_time: Optional[datetime] = None,
        hours: int = 12
    ) -> tuple[datetime, datetime]:
        """返回历史监测查询时间窗口。"""
        end_time = reference_time if reference_time else datetime.now()
        start_time = end_time - timedelta(hours=hours)
        return start_time, end_time

    def _is_historical_backfill(
        self,
        alert_dt: datetime,
        now: Optional[datetime] = None
    ) -> bool:
        """判断是否为历史报告回填。"""
        current_time = now if now else datetime.now()
        return alert_dt.date() < current_time.date()

    def _historical_forecast_unavailable_result(
        self,
        alert_dt: datetime,
        now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """历史回填时跳过实时预报，避免混入运行当天数据。"""
        current_time = now if now else datetime.now()
        alert_date = alert_dt.strftime("%Y-%m-%d")
        current_date = current_time.strftime("%Y-%m-%d")
        return {
            "status": "skipped",
            "success": False,
            "data": [],
            "summary": (
                f"历史回填报告日期为{alert_date}，当前运行日期为{current_date}。"
                "实时预报接口无法回溯该日期的当时预报，已跳过以避免混入运行当天数据。"
            )
        }

    async def _get_weather_forecast_for_alert(
        self,
        context,
        lat: float,
        lon: float,
        location_name: str,
        alert_dt: datetime
    ) -> Dict[str, Any]:
        """按告警日期决定是否调用实时天气预报接口。"""
        if self._is_historical_backfill(alert_dt):
            return self._historical_forecast_unavailable_result(alert_dt)

        return await self.tools["weather_forecast"].execute(
            context=context,
            lat=lat,
            lon=lon,
            location_name=location_name,
            forecast_days=15,
            past_days=1,
            hourly=True,
            daily=True
        )

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
        city: str,
        reference_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        从数据库获取空气质量数据

        包括：
        1. 未来7天日预报数据 (air_quality_forecast) - 优先calculated_aqi
        2. 周边8城市历史12小时数据 (CityAQIPublishHistory)

        Args:
            city: 城市名称
            reference_time: 分析基准时间，历史回填时使用告警时间

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
                    start_date, end_date = self._air_quality_forecast_window(reference_time)

                    forecast_query = select(AirQualityForecast).where(
                        and_(
                            AirQualityForecast.forecast_date >= start_date,
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
                    history_records = await self._get_city_history_from_sqlserver(
                        city,
                        reference_time=reference_time
                    )
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
        timeout_seconds: int = 90,
        meteo_source: str = "gfs0p25"  # 默认使用GFS数据源
    ) -> Dict[str, Any]:
        """获取轨迹分析 (带超时控制)

        Args:
            context: 执行上下文
            lat: 纬度
            lon: 经度
            start_time: 开始时间
            timeout_seconds: 超时时间（秒）
            meteo_source: 气象数据源（默认gfs0p25，推荐使用GFS避免GDAS1多文件问题）
        """
        try:
            logger.info(
                "trajectory_analysis_start",
                lat=lat,
                lon=lon,
                start_time=start_time,
                meteo_source=meteo_source,
                timeout=timeout_seconds
            )

            result = await asyncio.wait_for(
                self.tools["trajectory_analysis"].execute(
                    context=context,  # 使用传入的context
                    lat=lat,
                    lon=lon,
                    start_time=start_time,
                    hours=72,
                    heights=[100, 500, 1000],
                    direction="Backward",
                    meteo_source=meteo_source  # 传递气象数据源参数
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

            # 处理不同类型的响应对象
            response_text = ""
            if hasattr(response, 'text'):
                # 如果响应对象有text方法，调用它
                response_text = response.text
            elif isinstance(response, str):
                # 如果响应是字符串，直接使用
                response_text = response
            elif hasattr(response, 'content'):
                # 如果响应对象有content属性
                response_text = response.content
            elif hasattr(response, '__str__'):
                # 尝试转换为字符串
                response_text = str(response)
            else:
                # 未知类型，尝试强制转换
                try:
                    response_text = str(response)
                except Exception as e:
                    logger.error("response_conversion_failed", error=str(e))
                    response_text = f"响应转换失败: {type(response)}"

            cleaned_text = self._sanitize_report_text(response_text)

            return {
                "summary_text": cleaned_text if cleaned_text else "LLM返回空响应",
                "visuals": []  # 快速溯源不需要可视化，直接返回空列表
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "summary_generation_failed",
                error=error_msg,
                exc_info=True
            )

            # LLM调用失败时，生成简单的文本报告作为备用
            logger.info("generating_fallback_report")
            fallback_report = self._generate_fallback_report(
                results=results,
                city=city,
                pollutant=pollutant,
                alert_value=alert_value,
                alert_time=alert_time,
                error=error_msg
            )

            return {
                "summary_text": fallback_report,
                "visuals": []
            }

    def _sanitize_report_text(self, response_text: str) -> str:
        """去除模型可能输出的分析草稿，只保留正式报告正文。"""
        if not response_text:
            return ""

        text = str(response_text).strip()
        lines = text.splitlines()

        for index, line in enumerate(lines):
            normalized = line.strip()
            if (
                normalized.startswith("# ")
                and "污染溯源分析报告" in normalized
            ):
                return "\n".join(lines[index:]).strip()

        fallback_markers = (
            "## 一、综合结论",
            "一、综合结论",
            "# 济宁市污染溯源分析报告",
        )
        for marker in fallback_markers:
            position = text.find(marker)
            if position >= 0:
                return text[position:].strip()

        return text

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
                product_name = data.get("product_name", "中央气象台气象图")
                source_url = data.get("source_url", "")
                local_path = data.get("local_path", "")
                summaries["weather_situation"] = (
                    f"{product_name}已获取，可用于研判告警日大尺度天气系统和污染扩散背景。"
                    f"{f' 本地文件: {local_path}' if local_path else ''}"
                    f"{f' 原始来源: {source_url}' if source_url else ''}"
                )
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
1. ERA5历史数据：告警日前3天至前1天（D-3 ~ D-1）
2. Open-Meteo实时预报数据仅适用于当天或未来告警；历史回填报告如显示该项已跳过，不得使用运行当天数据替代
3. 空气质量历史数据应以告警时间为基准，覆盖告警前12小时
4. 空气质量预报数据应以告警日期为起点，覆盖告警日起7天；如数据库无对应日期数据，需明确说明缺失

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
服务器域名: http://219.135.180.51:56041

**重要**: 请在报告的"三、气象条件影响详细评估"章节末尾插入此图片。
使用Markdown格式，将服务器域名与相对路径拼接为完整URL：
![中央气象台天气形势图](http://219.135.180.51:56041{summaries['weather_situation_image_url']})
"""

        new_prompt += trajectory_image_section + weather_situation_image_section + """
---

【报告撰写要求】

只输出最终 Markdown 报告正文；禁止输出英文思考过程、分析草稿、写作计划、自我校正、检查清单或任何类似“Understand the Goal”“Analyze the Input Data”“Drafting the Report”的中间推理内容。报告必须直接从标题行开始。

请按照以下框架生成分析报告，使用流畅的段落式表述，避免过度条目化：

# {city}污染溯源分析报告

**污染物**: {pollutant} 
**生成时间**: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}

---

## 一、综合结论

[本节置于报告开头，概括本次污染过程的核心判断和关键结论，便于快速了解整体情况]

首先明确污染来源方向，基于后向轨迹分析指出主要源区和传输贡献强度（强/中/弱）。

然后判断气象条件影响，说明告警时段大气扩散能力（强/中/弱）及是否为静稳天气，评估气象条件对污染积累的促进作用。**重点分析告警当天截至告警时刻的边界层高度和风速变化趋势**。

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

**关键分析点**：利用告警当天截至告警时刻的小时数据，分析边界层高度和风速的日变化规律。

首先评估大气扩散能力。根据边界层高度（PBLH）判断垂直扩散条件，结合风速评估水平输送能力，综合给出扩散能力评价（强/中/弱）。**分析告警日前后边界层是否持续偏低导致污染累积**。

然后分析气象要素对污染的影响。说明温度对化学反应的作用、湿度对二次生成的影响、降水的清除作用（如有）。判断当前是否为静稳天气（低边界层、小风速）。

最后总结气象条件的总体影响，指出是否存在不利扩散条件。**基于告警日前后数据判断污染是从何时开始积累的**。

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
5. 使用政府公文常用表达，专业规范；预报数据被标记为跳过或缺失时，必须明确说明，不能编造未来趋势
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
        city: str,
        reference_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        从SQL Server数据库查询周边城市历史12小时空气质量数据

        数据库: XcAiDb @ 180.184.30.94:1433
        表名: CityAQIPublishHistory

        Args:
            city: 城市名称
            reference_time: 分析基准时间，历史回填时使用告警时间

        Returns:
            List[Dict]: 历史空气质量数据列表
        """
        import pyodbc
        import os
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

            # 计算时间范围 (基准时间前12小时)
            start_time, end_time = self._history_time_window(reference_time)

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

    def _generate_fallback_report(
        self,
        results: Dict[str, Any],
        city: str,
        pollutant: str,
        alert_value: float,
        alert_time: str,
        error: str
    ) -> str:
        """
        生成备用报告（当LLM调用失败时）

        Args:
            results: 各工具的执行结果
            city: 城市名称
            pollutant: 污染物类型
            alert_value: 告警浓度值
            alert_time: 告警时间
            error: LLM调用失败的错误信息

        Returns:
            str: 简单的文本报告
        """
        from datetime import datetime

        now = datetime.now()
        alert_dt = datetime.strptime(alert_time, "%Y-%m-%d %H:%M:%S")

        # 统计工具执行结果
        success_tools = []
        failed_tools = []

        for tool_name, result in results.items():
            if isinstance(result, dict) and result.get("success"):
                success_tools.append(tool_name)
            else:
                failed_tools.append(tool_name)

        # 构建报告
        report_lines = [
            f"# {city}污染溯源分析报告（备用报告）",
            f"",
            f"**污染物**: {pollutant}",
            f"**告警时间**: {alert_time}",
            f"**告警浓度**: {alert_value} μg/m³",
            f"**生成时间**: {now.strftime('%Y年%m月%d日 %H:%M')}",
            f"",
            f"---",
            f"",
            f"## ⚠️ 报告说明",
            f"",
            f"由于LLM服务调用失败（{error}），本报告为自动生成的简化版本。",
            f"以下为各工具的执行结果摘要：",
            f"",
            f"### ✅ 成功执行的工具 ({len(success_tools)}个)",
        ]

        for tool_name in success_tools:
            result = results.get(tool_name, {})
            summary = result.get("summary", "执行成功") if isinstance(result, dict) else "执行成功"
            report_lines.append(f"- **{tool_name}**: {summary}")

        report_lines.extend([
            f"",
            f"### ❌ 执行失败的工具 ({len(failed_tools)}个)",
        ])

        for tool_name in failed_tools:
            result = results.get(tool_name, {})
            error_msg = result.get("error", "未知错误") if isinstance(result, dict) else "未知错误"
            report_lines.append(f"- **{tool_name}**: {error_msg}")

        # 添加数据统计
        report_lines.extend([
            f"",
            f"---",
            f"",
            f"## 数据统计",
            f"",
            f"- 总工具数: {len(results)}",
            f"- 成功: {len(success_tools)}",
            f"- 失败: {len(failed_tools)}",
            f"",
            f"---",
            f"",
            f"*本报告由QuickTraceExecutor自动生成*",
        ])

        return "\n".join(report_lines)

    async def save_report(
        self,
        summary_text: str,
        city: str,
        alert_time: str,
        pollutant: str,
        alert_value: float,
        visuals: list = None,
        execution_time_seconds: float = None,
        has_trajectory: bool = False,
        warning_message: str = None,
    ) -> dict:
        """
        保存报告到文件和数据库

        Args:
            summary_text: 报告内容
            city: 城市名称
            alert_time: 告警时间
            pollutant: 污染物类型
            alert_value: 告警浓度值
            visuals: 可视化图表列表
            execution_time_seconds: 执行耗时
            has_trajectory: 是否包含轨迹分析
            warning_message: 警告信息

        Returns:
            dict: {"filepath": "...", "db_id": ...}
        """
        # 1. 保存到本地文件（可选，失败不影响数据库保存）
        filepath = None
        try:
            report_dir = project_root / "backend_data_registry" / "quick_trace_reports"
            report_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名（添加时间戳避免冲突）
            file_date_str = datetime.strptime(alert_time, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d")
            time_str = datetime.now().strftime("%H%M%S")
            filename = f"{city}_快速溯源报告_{file_date_str}_{time_str}.md"
            filepath = report_dir / filename

            # 保存报告
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(summary_text)
            except PermissionError:
                # 如果文件存在且只读，生成新的文件名（添加随机后缀）
                import uuid
                unique_suffix = uuid.uuid4().hex[:6]
                filename = f"{city}_快速溯源报告_{file_date_str}_{time_str}_{unique_suffix}.md"
                filepath = report_dir / filename
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(summary_text)

            logger.info(
                "report_saved_to_file",
                filepath=str(filepath),
                city=city,
                alert_time=alert_time
            )
        except Exception as e:
            logger.warning(
                "report_file_save_failed",
                city=city,
                error=str(e),
                message="File save failed, will continue with database save"
            )

        # 2. 保存到数据库
        db_id = None
        try:
            from app.db.repositories.quick_trace_repo import QuickTraceRepository

            repo = QuickTraceRepository()

            # 根据污染物类型确定单位
            unit = None
            if pollutant in ["PM2.5", "PM10", "O3", "NO2", "SO2"]:
                unit = "μg/m³"
            elif pollutant == "CO":
                unit = "mg/m³"

            # 生成数据库需要的日期格式 (YYYY-MM-DD)
            db_date_str = datetime.strptime(alert_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")

            db_id = await repo.save_analysis(
                analysis_date=db_date_str,
                alert_time=alert_time,
                pollutant=pollutant,
                alert_value=alert_value,
                unit=unit,
                summary_text=summary_text,
                visuals=visuals,
                execution_time_seconds=execution_time_seconds,
                has_trajectory=has_trajectory,
                warning_message=warning_message,
            )

            logger.info(
                "report_saved_to_database",
                db_id=db_id,
                city=city,
                pollutant=pollutant,
                alert_value=alert_value,
            )

        except Exception as e:
            logger.error(
                "report_database_save_failed",
                city=city,
                pollutant=pollutant,
                error=str(e),
                exc_info=True
            )
            # 数据库保存失败不影响文件保存

        return {
            "filepath": str(filepath),
            "db_id": db_id
        }


# ============================================================================
# 独立运行入口
# ============================================================================


class JiningQuickTraceFetcher(DataFetcher):
    """每日生成济宁市快速溯源报告。"""

    def __init__(
        self,
        city: str = "济宁市",
        schedule: str = "30 8 * * *",
        target_date_factory=None,
    ):
        super().__init__(
            name="jining_quick_trace_fetcher",
            description="济宁市快速溯源报告每日生成（按前一日自动推断污染事件）",
            schedule=schedule,
            version="1.0.0",
        )
        self.city = city
        self.target_date_factory = target_date_factory or self._default_target_date

    @staticmethod
    def _default_target_date() -> str:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    async def fetch_and_store(self):
        analysis_date = self.target_date_factory()
        logger.info(
            "jining_quick_trace_fetcher_started",
            city=self.city,
            analysis_date=analysis_date,
        )

        result = await run_once(city=self.city, analysis_date=analysis_date)

        logger.info(
            "jining_quick_trace_fetcher_completed",
            city=self.city,
            analysis_date=analysis_date,
            has_summary=bool(result.get("summary_text")),
            inferred_event=result.get("inferred_event"),
        )
        return result


async def run_once(city: str = "济宁市", analysis_date: str = None):
    """
    单次执行快速溯源分析，按分析日期自动推断污染事件

    Args:
        city: 城市名称
        analysis_date: 分析日期 (YYYY-MM-DD)
    """
    if not analysis_date:
        raise ValueError("单次执行必须提供 analysis_date，格式 YYYY-MM-DD")

    executor = QuickTraceExecutor()

    logger.info(
        "quick_trace_manual_run",
        city=city,
        analysis_date=analysis_date
    )

    result = await executor.execute_for_analysis_date(
        city=city,
        analysis_date=analysis_date
    )

    event = result.get("inferred_event")
    if not event:
        logger.warning(
            "quick_trace_manual_run_not_saved",
            city=city,
            analysis_date=analysis_date,
            reason="no_inferred_event",
        )
        return result

    # 保存报告
    if result.get("summary_text"):
        save_result = await executor.save_report(
            summary_text=result["summary_text"],
            city=city,
            alert_time=event["alert_time"],
            pollutant=event["pollutant"],
            alert_value=event["alert_value"],
            visuals=result.get("visuals", []),
            has_trajectory=result.get("has_trajectory", False),
            warning_message=result.get("warning_message"),
        )

        print(f"\n{'='*60}")
        print(f"报告已保存到: {save_result.get('filepath')}")
        print(f"数据库ID: {save_result.get('db_id')}")
        print(f"推断事件: {event.get('alert_time')} {event.get('pollutant')}={event.get('alert_value')}")
        print(f"{'='*60}\n")

        # 打印报告摘要
        print(result["summary_text"][:500] + "..." if len(result["summary_text"]) > 500 else result["summary_text"])

        if result.get("warning_message"):
            print(f"\n⚠️  {result['warning_message']}")

    return result


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="快速溯源执行器")
    parser.add_argument("--city", default="济宁市", help="城市名称")
    parser.add_argument("--analysis-date", required=True, help="分析日期，格式 YYYY-MM-DD")

    args = parser.parse_args()

    asyncio.run(run_once(
        city=args.city,
        analysis_date=args.analysis_date
    ))


if __name__ == "__main__":
    main()
