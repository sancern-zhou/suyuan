{{ config(
    materialized='table',
    tags=['daily'],
    indexes=[
        {'columns': ['rid']},
        {'columns': ['station_code', 'rstart']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '质控任务状态表(每日02:30增量,按年源表2026)。一行=一次质控任务的最新状态快照;jsonstr 为平台原始状态载荷(含执行步骤/结果值),质控详情工具直接解析它。窗口自2026-06-01,省控站过滤。'",
    ],
) }}

-- mart_qc_task_status_result: 质控任务状态(工具链本地化数据源)
-- 源: air_province_data.dbo.qc_his_task_status_result_2026(按年, 每年1月换年份)
-- 用途: jiangsu_fetch_qc_task_status 按 rid 取 jsonstr 还原质控详情(步骤/结果/日志/曲线)
with latest as (
    select s.*,
           row_number() over (
               partition by s.rid
               order by s.createtime desc nulls last, s.id desc
           ) as rn
    from {{ source('jiangsu_ods', 'qc_his_task_status_result_2026') }} s
)
select
    s.id,
    s.rid,
    s.uniquecode                                 as unique_code,
    s.stationcode                                as station_code,
    ds.station_name,
    ds.city_code,
    ds.city_name,
    s.stationname                                as source_station_name,
    s.poll,
    s.qctype                                     as qc_type,
    s.sstart,
    s.rstart,
    s.jsonstr,
    s.createtime,
    now()::timestamp                             as synced_at
from latest s
left join {{ ref('dim_station') }} ds
       on ds.station_code = s.stationcode
where s.rn = 1
