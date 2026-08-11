"""Registered event types available to task configuration clients."""

from pydantic import BaseModel, Field


class EventDefinition(BaseModel):
    event_type: str
    label: str
    description: str
    filter_fields: list[str] = Field(default_factory=list)


_EVENT_DEFINITIONS = {
    "yuncheng.alert.created": EventDefinition(
        event_type="yuncheng.alert.created",
        label="运城市空气质量告警",
        description="运城市小时盯守告警及溯源上下文已准备完成",
        filter_fields=["city", "alert_level", "target_pollutant"],
    ),
    "xuchang.daily_attainment.predicted_exceedance": EventDefinition(
        event_type="xuchang.daily_attainment.predicted_exceedance",
        label="许昌市日达标预测超标",
        description="许昌市当日PM2.5日均值或臭氧日最大8小时滑动平均预测超标",
        filter_fields=[
            "city", "target_date", "target_pollutant", "is_attainment_predicted",
            "notification_reason", "has_turnaround_opportunity",
        ],
    ),
    "xuchang.station_deviation.alert_created": EventDefinition(
        event_type="xuchang.station_deviation.alert_created",
        label="许昌站点空间偏差告警",
        description="许昌市站点小时浓度相对其他站点均值偏差超过阈值，场景一上风向分析上下文已生成",
        filter_fields=["city", "target_pollutant", "station_id"],
    ),
    "xuchang.station_deviation.escalated": EventDefinition(
        event_type="xuchang.station_deviation.escalated",
        label="许昌站点异常升级为输送分析",
        description="同站点同污染物连续两个有效小时触发场景二轨迹分析任务",
        filter_fields=["city", "target_pollutant", "station_id"],
    ),
    "xuchang.transport_analysis.completed": EventDefinition(
        event_type="xuchang.transport_analysis.completed",
        label="许昌输送路径分析完成",
        description="NOAA后向轨迹、本地输送走廊及轨迹覆盖企业筛查已完成",
        filter_fields=["city", "target_pollutant", "station_id", "diagnosis"],
    ),
}


def get_event_definitions() -> list[EventDefinition]:
    return list(_EVENT_DEFINITIONS.values())


def get_event_definition(event_type: str) -> EventDefinition | None:
    return _EVENT_DEFINITIONS.get(event_type)
