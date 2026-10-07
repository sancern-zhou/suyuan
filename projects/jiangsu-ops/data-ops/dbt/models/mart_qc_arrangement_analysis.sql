{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['status_cn']},
        {'columns': ['planned_time']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '质控任务安排宽表(每日全量)。status_cn 为平台安排状态文本(如 已过期/已完成);planned_time 为计划执行时间。执行结果与合格判定见 mart_qc_execution_analysis。'",
    ],
) }}

-- mart_qc_arrangement_analysis: 质控任务安排/完成状态宽表
-- 一行 = 一条平台安排的质控任务(含已过期/已完成等状态),回答"完成情况/哪些站点任务过期未完成"。
-- 依赖: jiangsu_ods.qc_arrangeresult(每日02:30全量)。
select
    a.id                     as id,
    a.stationcode            as station_code,
    a.stationname            as station_name,
    ds.city_code             as city_code,
    ds.city_name             as city_name,
    a.uniquecode             as uniquecode,
    a.poll                   as pollutant,
    a.ttype                  as task_type,
    a.tstatus                as tstatus,
    a.tstatusstr             as status_cn,
    a.stime                  as planned_time,
    a.rtime                  as result_time,
    a.createtime             as source_create_time,
    a.rid                    as rid,
    now()::timestamp         as synced_at
from {{ source('jiangsu_ods', 'qc_arrangeresult') }} a
left join {{ ref('dim_station') }} ds
       on ds.station_code = a.stationcode
