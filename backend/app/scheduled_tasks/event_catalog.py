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
    "jiangsu.smart_event.alarm": EventDefinition(
        event_type="jiangsu.smart_event.alarm",
        label="江苏智能事件告警线索",
        description="江苏告警线索证据包已准备完成，由智能事件 Agent 分析线索并定义最终事件类型",
        filter_fields=["clue_type", "site_id", "site_name"],
    ),
    "jiangsu.station_fault.detected": EventDefinition(
        event_type="jiangsu.station_fault.detected",
        label="江苏站点故障告警",
        description="江苏平台告警或监测异常已触发，且诊断证据包已准备完成",
        filter_fields=["source_type", "station_code", "alarm_type", "severity"],
    ),
    "jiangsu.fault_work_order.review_requested": EventDefinition(
        event_type="jiangsu.fault_work_order.review_requested",
        label="江苏故障工单审核",
        description="江苏故障工单到达省中心审核节点，且 SOP 审核证据包已准备完成",
        filter_fields=[
            "work_order_code",
            "station_code",
            "current_point",
            "sop_id",
            "fault_event_type",
        ],
    ),
    "jiangsu.data_audit.review_requested": EventDefinition(
        event_type="jiangsu.data_audit.review_requested",
        label="江苏数据审核AI复核",
        description="江苏审核平台站点已完成初审，平台证据包（初审结果/恒值/离群值三页签）已准备完成",
        filter_fields=[
            "station_code",
            "station_name",
            "city_name",
            "district_name",
            "audit_day",
            "station_state",
        ],
    ),
}


def get_event_definitions() -> list[EventDefinition]:
    return list(_EVENT_DEFINITIONS.values())


def get_event_definition(event_type: str) -> EventDefinition | None:
    return _EVENT_DEFINITIONS.get(event_type)
