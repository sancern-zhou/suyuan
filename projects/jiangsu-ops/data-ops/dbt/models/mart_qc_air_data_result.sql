{{ config(
    materialized='incremental',
    unique_key='id',
    tags=['daily'],
    indexes=[
        {'columns': ['station_code', 'poll', 'qc_type', 'timepoint']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '质控期间监测序列/曲线点(每日增量,按年源表2026)。一行=一站×一质控任务窗口×一时间点;timepoint 为监测时间,time 为平台记录时间。窗口自2026-07-01,省控站过滤。'",
    ],
) }}

-- mart_qc_air_data_result: 质控监测曲线点(增量)
-- 源: air_province_data.dbo.qc_his_air_data_result_2026(按年, 每年1月换年份)
-- 用途: jiangsu_fetch_qc_monitoring_curve 本地数据源 + 曲线语义查询
select
    a.id,
    a.uniquecode                                 as unique_code,
    a.stationcode                                as station_code,
    ds.station_name,
    ds.city_code,
    ds.city_name,
    a.stationname                                as source_station_name,
    a.poll,
    a.qctype                                     as qc_type,
    a.time,
    a.timepoint,
    a.datavalue,
    a.unit,
    a.datamark,
    a.flag,
    a.isqcing,
    a.createtime,
    now()::timestamp                             as synced_at
from {{ source('jiangsu_ods', 'qc_his_air_data_result_2026') }} a
left join {{ ref('dim_station') }} ds
       on ds.station_code = a.stationcode
{% if is_incremental() %}
where a.id > (select coalesce(max(id), 0) from {{ this }})
{% endif %}
