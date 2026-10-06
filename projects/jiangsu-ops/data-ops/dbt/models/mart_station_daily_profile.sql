{{ config(
    indexes=[
        {'columns': ['profile_date', 'station_code'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['city_name']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_station_daily_profile 站点日概况数据集（阶段二, 每日刷新）
-- 粒度: 一行 = 站点 × 日 (2026-07-01 起)
-- 用途: 全网态势时间序列、趋势对比、异常日识别 (smart_inspection/operations_analysis)
-- 口径: 当日工单=created_at 当日落盘; 当日完成=finish_time 当日; 当日告警=alarm_time 当日;
--       到站签到=signintime 当日(注: 7月以来源数据仅11条, 近乎空, 供后续补数)
-- ============================================================
with days as (
    select generate_series('2026-07-01'::date, current_date, interval '1 day')::date as d
), stations as (
    select s.stationcode, s.positionname,
           c.name as city_name
    from {{ source('jiangsu_ods', 'bsd_station') }} s
    left join {{ source('jiangsu_ods', 'bsd_city') }} c
           on c.code = case when length(s.areacode) >= 4
                            then rpad(left(s.areacode, 4), 6, '0')
                            else s.areacode end
          and c.level = '2'
), w as (
    select station_code, create_time::date as d,
           count(*) as created,
           count(*) filter (where is_overdue) as created_overdue
    from {{ ref('mart_work_order_analysis') }}
    group by station_code, create_time::date
), wf as (
    select station_code, finish_time::date as d, count(*) as finished
    from {{ ref('mart_work_order_analysis') }}
    where finish_time is not null
    group by station_code, finish_time::date
), a as (
    select station_code, alarm_time::date as d, count(*) as alarms
    from {{ ref('mart_alarm_event_analysis') }}
    group by station_code, alarm_time::date
), k as (
    select stationcode, signintime::date as d, count(*) as signins
    from {{ source('jiangsu_ods', 'opa_kq_attendance') }}
    group by stationcode, signintime::date
)
select
    days.d                                     as profile_date,
    st.stationcode                             as station_code,
    st.positionname                            as station_name,
    st.city_name                               as city_name,
    coalesce(w.created, 0)                     as work_orders_created,
    coalesce(wf.finished, 0)                   as work_orders_finished,
    coalesce(w.created_overdue, 0)             as overdue_orders_created,
    coalesce(a.alarms, 0)                      as alarms,
    coalesce(k.signins, 0)                     as attendance_signins,
    now()::timestamp                           as refreshed_at
from days
cross join stations st
left join w  on w.station_code = st.stationcode and w.d = days.d
left join wf on wf.station_code = st.stationcode and wf.d = days.d
left join a  on a.station_code = st.stationcode and a.d = days.d
left join k  on k.stationcode = st.stationcode and k.d = days.d
where coalesce(w.created, 0) + coalesce(wf.finished, 0)
    + coalesce(a.alarms, 0) + coalesce(k.signins, 0) > 0
