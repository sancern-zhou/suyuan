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
        description="许昌市站点5分钟或PM2.5小时浓度相对其他站点偏差超过阈值，监测对比、气象和质控证据已生成",
        filter_fields=["city", "target_pollutant", "station_id"],
    ),
    "xuchang.station_deviation.episode_closed": EventDefinition(
        event_type="xuchang.station_deviation.episode_closed",
        label="许昌站点空间偏差过程结束",
        description="同站点同污染物连续小时异常过程已结束",
        filter_fields=["city", "target_pollutant", "station_id"],
    ),
    "xuchang.station_daily_pollution.confirmed": EventDefinition(
        event_type="xuchang.station_daily_pollution.confirmed",
        label="许昌站点小时高值确认",
        description="站点小时浓度相对同小时其他站点明显偏高，达到小时异常阈值",
        filter_fields=["city", "target_date", "target_pollutant", "station_id"],
    ),
    "xuchang.station_daily_pollution.review_completed": EventDefinition(
        event_type="xuchang.station_daily_pollution.review_completed",
        label="许昌昨日站点污染回顾完成",
        description="许昌昨日站点小时数据例行回顾已完成，无论是否发现小时异常均触发",
        filter_fields=["city", "target_date"],
    ),
    "xuchang.station_daily_source_analysis.requested": EventDefinition(
        event_type="xuchang.station_daily_source_analysis.requested",
        label="许昌站点日污染溯源分析已请求",
        description="站点日污染超标已创建唯一的场景二溯源分析任务",
        filter_fields=["city", "target_date", "target_pollutant", "station_id"],
    ),
    "xuchang.station_daily_source_analysis.completed": EventDefinition(
        event_type="xuchang.station_daily_source_analysis.completed",
        label="许昌站点日污染溯源分析完成",
        description="超标日小时污染回顾及确定性污染机制、传输和气象证据已完成",
        filter_fields=["city", "target_date", "target_pollutant", "station_id", "diagnosis"],
    ),
}


def get_event_definitions() -> list[EventDefinition]:
    return list(_EVENT_DEFINITIONS.values())


def get_event_definition(event_type: str) -> EventDefinition | None:
    return _EVENT_DEFINITIONS.get(event_type)
