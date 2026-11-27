"""Registered event types available to task configuration clients."""

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.project_config.models import ProjectManifest


class EventDefinition(BaseModel):
    event_type: str
    label: str
    description: str
    filter_fields: list[str] = Field(default_factory=list)


_EVENT_DEFINITIONS = {
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
    "xuchang.pollution_cause_analysis.triggered": EventDefinition(
        event_type="xuchang.pollution_cause_analysis.triggered",
        label="许昌PM2.5高于相邻五市触发原因分析",
        description="许昌市PM2.5日均浓度高于相邻五市（郑汴平漯周）均值20%以上，触发污染原因分析通报推送",
        filter_fields=["city", "target_date", "triggered", "deviation_percent"],
    ),
    "xuchang.monthly_review.completed": EventDefinition(
        event_type="xuchang.monthly_review.completed",
        label="许昌月度特征分析证据已生成",
        description="每月2日上月城市浓度对比、排名、气象、站点告警与企业背景证据包已冻结，推送APP月度通报",
        filter_fields=["city", "month"],
    ),
    "xuchang.enterprise_clue_weekly.completed": EventDefinition(
        event_type="xuchang.enterprise_clue_weekly.completed",
        label="许昌企业核查线索周报证据已生成",
        description="每周一汇总上周站点告警的上风向候选企业筛查线索（代理口径，不认定责任），推送APP周报",
        filter_fields=["city"],
    ),
}


def _event_belongs_to_project(event_type: str, project: str) -> bool:
    """按事件命名空间归属过滤：事件类型以项目事件前缀开头即归属该项目。

    事件类型约定 ``<项目事件前缀>.<事件名>``；前缀取 manifest.project 及其去掉部署
    后缀的首段（jiangsu-ops -> jiangsu，兼容分支自持目录中已有的 jiangsu.* 命名）。
    事件目录中的项目专属事件（如 xuchang.*）不再向其他项目部署暴露。
    """
    if not project:
        return True
    prefixes = [f"{project}."]
    head = project.split("-")[0]
    if head and head != project:
        prefixes.append(f"{head}.")
    return event_type.startswith(tuple(prefixes))


def get_event_definitions(manifest: "ProjectManifest | None" = None) -> list[EventDefinition]:
    """返回事件目录；传入 manifest 时按部署项目过滤命名空间。"""
    if manifest is None:
        return list(_EVENT_DEFINITIONS.values())
    return [
        definition
        for definition in _EVENT_DEFINITIONS.values()
        if _event_belongs_to_project(definition.event_type, manifest.project)
    ]


def get_event_definition(
    event_type: str, manifest: "ProjectManifest | None" = None
) -> EventDefinition | None:
    definition = _EVENT_DEFINITIONS.get(event_type)
    if definition is None:
        return None
    if manifest is not None and not _event_belongs_to_project(
        event_type, manifest.project
    ):
        return None
    return definition
