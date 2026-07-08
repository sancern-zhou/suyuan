"""
City Pollution Event Fetcher

定时巡检城市污染过程，识别污染事件并收集证据。
"""
from __future__ import annotations

from typing import List
from pathlib import Path
from datetime import datetime

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.pollution_event_monitor import (
    MonitorConfig,
    run_pollution_event_monitor,
)

logger = structlog.get_logger()


class CityPollutionEventFetcher(DataFetcher):
    """
    城市污染过程事件抓取器

    功能：
    - 定时巡检指定城市最近N小时的小时监测数据
    - 识别污染过程（AQI/PM2.5/PM10/O3等超标事件）
    - 自动收集相关站点数据、气象数据、组分数据
    - 生成结构化证据包（evidence_pack.json）
    - 不需要 Agent 参与，后台自动运行

    输出位置：backend_data_registry/pollution_process_events/{city}/
    """

    # 默认配置
    DEFAULT_CITIES = ["广州", "深圳", "佛山", "东莞"]
    DEFAULT_HOURS = 24
    DEFAULT_STATION_TYPE = ["国控", "省控"]  # 同时抓取国控和省控站点
    DEFAULT_OUTPUT_ROOT = None  # 使用默认路径 backend_data_registry/pollution_process_events/
    DEFAULT_FORCE_COLLECT = False
    DEFAULT_INCLUDE_COMPONENTS = True
    DEFAULT_AUTO_ENHANCE_EVIDENCE = True

    def __init__(
        self,
        cities: List[str] | None = None,
        hours: int = DEFAULT_HOURS,
        station_type: List[str] | None = None,
        output_root: Path | None = DEFAULT_OUTPUT_ROOT,
        force_collect: bool = DEFAULT_FORCE_COLLECT,
        include_components: bool = DEFAULT_INCLUDE_COMPONENTS,
        auto_enhance_evidence: bool = DEFAULT_AUTO_ENHANCE_EVIDENCE,
        include_trajectory: bool = True,
        include_upwind_enterprises: bool = True,
        include_component_models: bool = True,
    ):
        """
        初始化城市污染事件抓取器

        Args:
            cities: 监控城市列表，默认为广州、深圳、佛山、东莞
            hours: 回看小时数，默认24小时
            station_type: 站点类型列表，默认["国控", "省控"]
            output_root: 输出目录，默认为 backend_data_registry/pollution_process_events/
            force_collect: 是否强制收集数据（即使没有检测到事件）
            include_components: 是否包含组分数据（PM2.5离子/碳/地壳、VOCs）
            auto_enhance_evidence: 是否在证据包中自动运行轨迹、上风向企业和组分模型分析
            include_trajectory: 是否运行后向轨迹分析
            include_upwind_enterprises: 是否运行高值站点上风向企业筛选
            include_component_models: 是否按主污染物运行组分模型分析
        """
        super().__init__(
            name="city_pollution_event_fetcher",
            description="城市污染过程自动识别与证据收集",
            schedule="0 * * * *",  # 每小时整点运行
            version="1.0.0",
        )

        # 配置参数
        self.cities = cities or self.DEFAULT_CITIES
        self.hours = hours
        self.station_type = station_type or self.DEFAULT_STATION_TYPE
        self.output_root = output_root
        self.force_collect = force_collect
        self.include_components = include_components
        self.auto_enhance_evidence = auto_enhance_evidence
        self.include_trajectory = include_trajectory
        self.include_upwind_enterprises = include_upwind_enterprises
        self.include_component_models = include_component_models

        logger.info(
            "city_pollution_event_fetcher_initialized",
            cities=self.cities,
            hours=self.hours,
            station_type=self.station_type,
            force_collect=force_collect,
            include_components=include_components,
            auto_enhance_evidence=auto_enhance_evidence,
        )

    async def fetch_and_store(self):
        """
        执行污染事件检测和证据收集

        工作流程：
        1. 获取指定城市最近N小时的小时监测数据
        2. 运行污染事件检测规则（AQI/PM2.5/PM10/O3等超标）
        3. 对检测到的事件，收集补充数据（站点、气象、组分）
        4. 生成结构化证据包并保存到磁盘
        """
        try:
            # 创建配置
            config = MonitorConfig(
                cities=self.cities,
                hours=self.hours,
                station_type=self.station_type,
                output_root=self.output_root,
                force_collect=self.force_collect,
                include_components=self.include_components,
                auto_enhance_evidence=self.auto_enhance_evidence,
                include_trajectory=self.include_trajectory,
                include_upwind_enterprises=self.include_upwind_enterprises,
                include_component_models=self.include_component_models,
                end_time=datetime.now(),
                session_id=f"fetcher_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            )

            # 运行检测
            result = await run_pollution_event_monitor(
                config=config,
                context=None,  # Fetcher 不需要 ExecutionContext
            )

            # 记录结果
            event_count = result.get("event_count", 0)
            artifact_count = len(result.get("event_artifacts", []))

            logger.info(
                "city_pollution_event_fetcher_completed",
                cities=self.cities,
                hours=self.hours,
                event_count=event_count,
                artifact_count=artifact_count,
                output_root=result.get("output_root"),
                summary=result.get("summary"),
            )

            return result

        except Exception as e:
            logger.error(
                "city_pollution_event_fetcher_failed",
                cities=self.cities,
                error=str(e),
                exc_info=True,
            )
            raise
