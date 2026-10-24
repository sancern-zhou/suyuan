{{ config(
    indexes=[
        {'columns': ['station_id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_station_alarm_status 广东站点当前告警态势快照
-- 口径（2026-10-25 勘察确认）:
--   源   = Alm_Home（一行 = 一个站点，每日刷新；实测源系统只推送"告警中"站点
--          —— 当日 63 站全部为"紧急"，正常站点不入表，故 is_alarming 恒为 true）
--   状态 = DictionaryItemText（当前实测仅"紧急"）；告警描述见 latest_alarm_desc
--   用途 = "当前告警站点清单"；正常站点数不可从本表得出；历史流水见 mart_alarm_notify_analysis；
--          本表同时是 dim_station 城市维度的补充来源（仅覆盖推送过的站点）
-- 刷新: 全量重建（每日）
-- ============================================================
select
    h.stationid                                    as station_id,
    d.station_code                                 as station_code,
    h.stationname                                  as station_name,
    h.regionid                                     as city_code,
    h.regionname                                   as city_name,
    h.typename                                     as station_type_name,
    h.username                                     as manager_name,
    h.dictionaryitemtext                           as alarm_status,
    (coalesce(nullif(trim(h.dictionaryitemtext), ''), '正常') <> '正常') as is_alarming,
    h.alarmlevel                                   as alarm_level,
    h.content                                      as latest_alarm_desc,
    h.alarmtime                                    as latest_alarm_time,
    h.isinterrupt                                  as is_interrupt,
    h.stationunit                                  as station_unit,
    now()::timestamp                               as refreshed_at
from {{ source('guangdong_ods', 'alm_home') }} h
left join {{ ref('dim_station') }} d
       on d.station_id = h.stationid
