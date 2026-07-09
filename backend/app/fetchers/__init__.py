"""
Data Fetching Backend

定时从外部API爬取数据，存入云数据库的后台程序
"""

from app.fetchers.base.scheduler import FetcherScheduler
from app.fetchers.consultation import ConsultationFileFetcher
from app.fetchers.consultation.monthly import MonthlyConsultationFileFetcher
from app.fetchers.consultation.annual_ytd import AnnualYtdConsultationFileFetcher
from app.fetchers.consultation.monthly_supplement_fetchers import (
    MonthlyDistrictPollutantRankingFetcher,
    MonthlyMeteorologySupportFetcher,
    MonthlyPollutionEventsComponentsFetcher,
    MonthlyStationHighValuesFetcher,
)
from app.fetchers.air_quality_data_quality_monitor import AirQualityDataQualityFetcher
from app.fetchers.city_pollution_event_monitor import CityPollutionEventFetcher
from app.fetchers.fault_diagnosis import FaultDiagnosisFetcher
from app.fetchers.tenders import TenderInformationFetcher
from app.fetchers.quick_trace import JiningQuickTraceFetcher
from app.fetchers.yuncheng_trial import YunchengTrialFetcher
from app.fetchers.weather.nmc_observed_fetcher import NMCObservedWeatherFetcher
from app.fetchers.weather.open_meteo_air_quality_forecast_fetcher import (
    OpenMeteoAirQualityForecastFetcher,
)

def create_scheduler() -> FetcherScheduler:
    """
    创建并配置Fetcher调度器

    Returns:
        FetcherScheduler实例
    """
    scheduler = FetcherScheduler()

    # 注册所有Fetchers
    scheduler.register(ConsultationFileFetcher())  # 会商文件批量更新（当月累积）
    scheduler.register(MonthlyConsultationFileFetcher())  # 月度完整会商文件（上个月完整版，手动触发）
    scheduler.register(AnnualYtdConsultationFileFetcher())  # 年度累计会商文件（每月4号生成截至上个月月末）
    scheduler.register(MonthlyDistrictPollutantRankingFetcher())  # 月度区县污染物排名补充数据
    scheduler.register(MonthlyStationHighValuesFetcher())  # 月度高值站点补充数据
    scheduler.register(MonthlyPollutionEventsComponentsFetcher())  # 月度污染时段及组分补充数据
    scheduler.register(MonthlyMeteorologySupportFetcher())  # 月度气象支撑补充数据
    scheduler.register(AirQualityDataQualityFetcher())  # 空气质量数据质量巡检
    scheduler.register(CityPollutionEventFetcher())  # 城市污染过程告警
    scheduler.register(FaultDiagnosisFetcher())  # 疑似设备或数据故障原因诊断
    scheduler.register(TenderInformationFetcher())  # 招投标信息每日抓取
    scheduler.register(JiningQuickTraceFetcher())  # 济宁市快速溯源报告每日生成
    scheduler.register(YunchengTrialFetcher())  # 运城市驻场试用场景小时数据盯守
    scheduler.register(NMCObservedWeatherFetcher())  # 许昌、运城NMC小时气象实况
    scheduler.register(OpenMeteoAirQualityForecastFetcher())  # 运城、许昌未来72小时空气质量预报

    return scheduler


__all__ = ['create_scheduler', 'FetcherScheduler']
