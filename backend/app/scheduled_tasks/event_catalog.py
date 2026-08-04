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
}


def get_event_definitions() -> list[EventDefinition]:
    return list(_EVENT_DEFINITIONS.values())


def get_event_definition(event_type: str) -> EventDefinition | None:
    return _EVENT_DEFINITIONS.get(event_type)
