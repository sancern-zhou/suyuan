{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['status_cn']},
        {'columns': ['planned_time']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '质控任务安排宽表(每日全量,省控站统一口径=启用省控站101个)。status_cn 为平台安排状态文本(如 已过期/已完成);planned_time 为计划执行时间。执行结果与合格判定见 mart_qc_execution_analysis。停用省控站与非省控类型站(Voc等)不入本表。'",
    ],
) }}

-- mart_qc_arrangement_analysis: 质控任务安排/完成状态宽表
-- 一行 = 一条平台安排的质控任务(含已过期/已完成等状态),回答"完成情况/哪些站点任务过期未完成"。
-- 依赖: jiangsu_ods.qc_arrangeresult(每日02:30全量)。
-- 站点范围(2026-10-14 治理): 省控站统一口径=启用省控站101个(dim_station.is_active_provincial);
-- 与 mart_qc_execution_analysis(质控执行)同口径, 停用省控站与Voc等非省控类型不入本表。
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
where ds.is_active_provincial
