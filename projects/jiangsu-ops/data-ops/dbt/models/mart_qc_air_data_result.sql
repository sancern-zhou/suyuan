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
-- 部署注意: 本模型为 incremental(on_schema_change 默认 ignore), 新增列不会自动加到已存在的表。
-- 给本模型加列后(如 2026-10 的 datavalue_numeric, 下游 QcAirData Cube 数值聚合读该列)必须先执行
--   dbt run --full-refresh -s mart_qc_air_data_result
-- 再重启 Cube; 否则存量行新列为 NULL → Cube 数值聚合静默只统计增量新行。
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
    -- 源列 datavalue 实测即 numeric(2026-10-19 部署发现; 上游按"文本原值+正则"写的
    -- 版本在 numeric 上报 btrim(numeric) 不存在), 直接转 double 作聚合列, 与 datavalue 同值
    a.datavalue::double precision               as datavalue_numeric,
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
