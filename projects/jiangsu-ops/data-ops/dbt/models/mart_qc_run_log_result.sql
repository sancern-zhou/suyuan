{{ config(
    materialized='incremental',
    unique_key='id',
    tags=['daily'],
    indexes=[
        {'columns': ['rid', 'record_time']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '质控任务运行日志(每日增量,按年源表2026)。一行=一条运行事件;strEvent 为事件分类文本。窗口自2026-07-01,省控站过滤。'",
    ],
) }}

-- mart_qc_run_log_result: 质控运行日志(增量)
-- 源: air_province_data.dbo.qc_his_run_log_result_2026(按年, 每年1月换年份)
-- 用途: jiangsu_fetch_qc_run_logs 本地数据源 + 运行日志语义查询
select
    r.id,
    r.rid,
    r.uniquecode                                 as unique_code,
    r.stationcode                                as station_code,
    ds.station_name,
    ds.city_code,
    ds.city_name,
    r.stationname                                as source_station_name,
    r.poll,
    r.qctype                                     as qc_type,
    r.sstart,
    r.rstart,
    r.eventtype                                  as event_type,
    r.strevent                                   as str_event,
    r.message,
    r.recordtime                                 as record_time,
    r.target,
    r.username                                   as user_name,
    r.createtime,
    now()::timestamp                             as synced_at
from {{ source('jiangsu_ods', 'qc_his_run_log_result_2026') }} r
left join {{ ref('dim_station') }} ds
       on ds.station_code = r.stationcode
{% if is_incremental() %}
where r.id > (select coalesce(max(id), 0) from {{ this }})
{% endif %}
