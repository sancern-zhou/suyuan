"""Registered event types available to task configuration clients."""

from pydantic import BaseModel, Field


class EventDefinition(BaseModel):
    event_type: str
    label: str
    description: str
    filter_fields: list[str] = Field(default_factory=list)


_EVENT_DEFINITIONS: dict[str, EventDefinition] = {
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
    "xuchang.city_pollution_episode.confirmed": EventDefinition(
        event_type="xuchang.city_pollution_episode.confirmed",
        label="许昌城市污染过程触发",
        description="国控站小时发布AQI持续轻度污染或站点相对偏差已识别",
        filter_fields=["city", "station_id", "target_pollutant"],
    ),
    "xuchang.city_source_analysis.requested": EventDefinition(
        event_type="xuchang.city_source_analysis.requested",
        label="许昌城市污染过程溯源已请求",
        description="逐小时污染过程已生成唯一的轨迹与气象诊断任务",
        filter_fields=["city", "station_id", "target_pollutant"],
    ),
    "xuchang.city_source_analysis.completed": EventDefinition(
        event_type="xuchang.city_source_analysis.completed",
        label="许昌城市污染过程溯源已完成",
        description="逐小时污染过程的确定性证据包已冻结并可生成独立报告",
        filter_fields=["city", "station_id", "target_pollutant", "diagnosis"],
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
