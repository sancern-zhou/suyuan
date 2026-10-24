{{ config(
    indexes=[
        {'columns': ['alarm_id'], 'unique': True},
        {'columns': ['station_id']},
        {'columns': ['notify_time']},
        {'columns': ['alarm_type']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_alarm_notify_analysis 广东站点告警通知分析宽表
-- 口径（2026-10-25 勘察确认）:
--   源   = ALM_ALARM（一行 = 一条告警通知记录，含短信/邮件发送渠道）
--   注意 = 本库告警为"通知流水"，无处理闭环状态（未处理率不可评估）；
--          站点当前告警态势（正常/紧急）见 mart_station_alarm_status；
--          ALM_SUMMARY 自 2020 年停更，禁止使用
--   类型 = 告警类型从 CONTENT 前缀解析（"2026-10-24 23：站点断数" → 站点断数）
--   级别 = ALARMLEVEL 当前实测恒为 9（通知级），仅保留原值
--   站点 = STATIONID 经 dim_station.station_id 关联（实测匹配率 99.5%）
-- 刷新: 全量重建（今年通知量约 20 万行，小时级成本可忽略）
-- ============================================================
with alarm as (
    select
        a.alarmid            as alarm_id,
        a.stationid          as station_id,
        a.alarmtime          as alarm_time,
        a.content            as content,
        a.ddalarmstyle       as notify_channels,
        a.contactuserid      as contact_user_id,
        a.dataid             as data_id,
        a.summaryid          as summary_id
    from {{ source('guangdong_ods', 'alm_alarm') }} a
    where a.alarmtime >= '{{ var("phase1_since", "2026-01-01") }}'::timestamp
)
select
    a.alarm_id,
    a.station_id,
    d.station_code                                           as station_code,
    d.station_name                                           as station_name,
    d.station_type_name                                      as station_type_name,
    d.city_code                                              as city_code,
    d.city_name                                              as city_name,
    -- 告警类型（2026-10-25 实测仅三种内容形态，分类硬编码并在 registry 登记）:
    --   "{date} {hour}：站点断数" / "{date} {hour}时，小时浓度：{v}，上限:{l}" /
    --   "{device}，{date} {hour}，仪器断数"
    case
        when a.content like '%站点断数%' then '站点断数'
        when a.content like '%小时浓度%' then '小时浓度超标'
        when a.content like '%仪器断数%' then '仪器断数'
        when a.content like '%质控结果%' then '质控异常'
        else trim(split_part(a.content, '：', 2))
    end                                                      as alarm_type,
    a.content                                                as content,
    a.alarm_time                                             as notify_time,
    date_trunc('day', a.alarm_time)                          as notify_date,
    a.notify_channels                                        as notify_channels,
    a.contact_user_id                                        as contact_user_id,
    a.data_id                                                as data_id,
    a.summary_id                                             as summary_id,
    now()::timestamp                                         as refreshed_at
from alarm a
left join {{ ref('dim_station') }} d
       on d.station_id = a.station_id
