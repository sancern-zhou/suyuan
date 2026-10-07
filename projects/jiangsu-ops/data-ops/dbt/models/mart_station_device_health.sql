{{ config(
    indexes=[
        {'columns': ['station_code'], 'unique': True},
        {'columns': ['city_code']},
        {'columns': ['risk_level']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_station_device_health 站点设备健康数据集（阶段二）
-- 粒度: 一行 = 一个站点 (bsd_station 全量, 含无工单/告警站点)
-- 指标窗口: 工单/超期/响应 取近30天, 告警取近7天/30天
-- risk_level 规则(代理口径, 待业务确认):
--   高 = (30天工单>=5 且 超期率>=50%) 或 未处理告警>=10
--   中 = (30天工单>=3 且 超期率>=30%) 或 未处理告警>=5
--   其余为 低; 无工单无告警站点 = 稳定
-- 依赖: mart_work_order_analysis / mart_alarm_event_analysis 先刷新(dbt ref 保证)
-- ============================================================
with w as (
    select station_code,
           count(*) filter (where create_time >= now() - interval '30 days') as wo_30d,
           count(*) filter (where create_time >= now() - interval '30 days' and is_overdue) as od_30d,
           count(*) filter (where create_time >= now() - interval '30 days' and is_repeat_fault) as rp_30d,
           round(avg(response_minutes) filter (where create_time >= now() - interval '30 days'), 1) as avg_resp,
           max(create_time) as last_wo
    from {{ ref('mart_work_order_analysis') }}
    group by station_code
), a as (
    select station_code,
           count(*) filter (where alarm_time >= now() - interval '7 days') as al_7d,
           count(*) filter (where alarm_time >= now() - interval '30 days') as al_30d,
           count(*) filter (where is_unresolved) as unres,
           max(alarm_time) as last_al
    from {{ ref('mart_alarm_event_analysis') }}
    group by station_code
), d as (
    select stationcode, count(*) as dev_n
    from {{ source('jiangsu_ods', 'bsd_device') }}
    group by stationcode
)
select
    s.stationcode                      as station_code,
    s.positionname                     as station_name,
    s.areacode                         as city_code,
    c.name                             as city_name,
    s.status                           as station_status,
    s.ismonitor                        as is_monitor,
    coalesce(d.dev_n, 0)               as device_count,
    coalesce(w.wo_30d, 0)              as work_orders_30d,
    coalesce(w.od_30d, 0)              as overdue_orders_30d,
    case when coalesce(w.wo_30d, 0) > 0
         then round(w.od_30d::numeric / w.wo_30d, 3) else 0 end
                                       as overdue_rate_30d,
    coalesce(w.rp_30d, 0)              as repeat_fault_orders_30d,
    w.avg_resp                         as avg_response_minutes_30d,
    coalesce(a.al_7d, 0)               as alarms_7d,
    coalesce(a.al_30d, 0)              as alarms_30d,
    coalesce(a.unres, 0)               as unresolved_alarms,
    a.last_al                          as last_alarm_time,
    w.last_wo                          as last_work_order_time,
    case
        when coalesce(w.wo_30d, 0) = 0 and coalesce(a.al_30d, 0) = 0 then '稳定'
        when (coalesce(w.wo_30d,0) >= 5 and coalesce(w.od_30d,0)::numeric / w.wo_30d >= 0.5)
          or coalesce(a.unres, 0) >= 10 then '高'
        when (coalesce(w.wo_30d,0) >= 3 and coalesce(w.od_30d,0)::numeric / w.wo_30d >= 0.3)
          or coalesce(a.unres, 0) >= 5 then '中'
        else '低'
    end                                as risk_level,
    now()::timestamp                   as refreshed_at
from {{ source('jiangsu_ods', 'bsd_station') }} s
left join {{ source('jiangsu_ods', 'bsd_city') }} c
       on c.code = case when length(s.areacode) >= 4
                        then rpad(left(s.areacode, 4), 6, '0')
                        else s.areacode end
      and c.level = '2'
left join w on w.station_code = s.stationcode
left join a on a.station_code = s.stationcode
left join d on d.stationcode = s.stationcode
