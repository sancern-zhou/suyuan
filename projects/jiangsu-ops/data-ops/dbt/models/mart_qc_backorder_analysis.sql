{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['start_time']},
        {'columns': ['state']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '质控补测/回调安排日志宽表(每日全量,窗口>=2026-07-01)。一行=一条补测安排(站点×小时×污染物)。state/datatype 为平台原始枚举(语义待平台确认);uniquecode 可关联质控执行结果(qc_historyresult)判断补测背景;勿关联 qc_arrangeresult(该表 uniquecode 为任务组代码)。'",
    ],
) }}

-- mart_qc_backorder_analysis: 质控补测/回调安排日志宽表。
-- 回答: 哪些站点/因子被安排补测、当前状态、补测是否集中爆发(站点×日聚合=风暴预警)。
-- 质控闭环下游: mart_qc_execution_analysis(合格/不合格) → 本表(平台补测处置) → 复核结果。
-- 口径: state 1/2/3/6 与 datatype 1/2/3/6 为平台原始枚举,中文语义待平台确认,契约中不得编造。
select
    b.id                     as id,
    b.stationcode            as station_code,
    ds.station_name          as station_name,
    ds.city_code             as city_code,
    ds.city_name             as city_name,
    b.uniquecode             as uniquecode,
    nullif(btrim(b.pollutantname), '') as pollutant_name,
    b.datatype               as datatype,
    b.state                  as state,
    b.start_time             as start_time,
    b.end_time               as end_time,
    b.create_time            as created_at,
    btrim(b.operator)        as operator,
    now()::timestamp         as synced_at
from {{ source('jiangsu_ods', 'qc_backorderarrangelog') }} b
left join {{ ref('dim_station') }} ds
       on ds.station_code = b.stationcode
