{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['city_code']},
        {'columns': ['alarm_time']},
        {'columns': ['is_unresolved']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_alarm_event_analysis 江苏告警事件分析数据集（阶段二）
-- 粒度: 一行 = 一条站点告警 (alm_summary, 2026-07-01 起)
-- 口径:
--   告警持续 = removetime - alarmtime; 处理时长 = handletime - alarmtime
--   状态翻译: ddalarmstate 1=未处理 3=已解除(经数据验证: 状态3全部有解除时间)
--   关联工单 = 告警发生后 24h 内同站创建的工单数(来自 mart_work_order_analysis)
--   alarmlevel 翻译: urgent=紧急 secondary=中级 commonly=一般(按平台惯例, 待业务确认)
-- 刷新: 全量重建, 依赖 mart_work_order_analysis 先刷新(dbt ref 依赖保证顺序)
-- ============================================================
select
    a.id                                    as id,
    a.stacode                               as station_code,
    s.positionname                          as station_name,
    s.areacode                              as city_code,
    c.name                                  as city_name,
    a.deviceid                              as device_id,
    a.content                               as alarm_content,
    a.alarmlevel                            as alarm_level,
    case a.alarmlevel
        when 'urgent' then '紧急'
        when 'secondary' then '中级'
        when 'commonly' then '一般'
        else a.alarmlevel
    end                                     as alarm_level_cn,
    a.ddalarmstate                          as alarm_state,
    case a.ddalarmstate when 1 then '未处理' when 3 then '已解除' end
                                            as alarm_state_cn,
    a.ddruletype                            as rule_type,
    a.alarmtime                             as alarm_time,
    a.handletime                            as handle_time,
    a.removetime                            as remove_time,
    case when a.removetime is not null
         then round(extract(epoch from (a.removetime - a.alarmtime)) / 60.0, 1)
    end                                     as duration_minutes,
    case when a.handletime is not null
         then round(extract(epoch from (a.handletime - a.alarmtime)) / 60.0, 1)
    end                                     as handle_minutes,
    a.removetime is null                    as is_unresolved,
    coalesce(wo.linked_orders, 0)           as linked_work_orders_24h,
    greatest(a.removetime, a.handletime)    as source_updated_at,
    now()::timestamp                        as refreshed_at
from {{ source('jiangsu_ods', 'alm_summary') }} a
left join {{ source('jiangsu_ods', 'bsd_station') }} s
       on s.stationcode = a.stacode
left join {{ source('jiangsu_ods', 'bsd_city') }} c
       on c.code = case when length(s.areacode) >= 4
                        then rpad(left(s.areacode, 4), 6, '0')
                        else s.areacode end
      and c.level = '2'
left join lateral (
    select count(*) as linked_orders
    from {{ ref('mart_work_order_analysis') }} w
    where w.station_code = a.stacode
      and w.create_time between a.alarmtime and a.alarmtime + interval '24 hours'
) wo on true
