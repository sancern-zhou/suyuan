{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['qc_date']},
        {'columns': ['city_code']},
        {'columns': ['is_qualified']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '质控执行结果宽表(2026-07-01起)。result_cn 为平台原始判定文本(合格/不合格);is_qualified 由该文本推导。任务类型=零点检查/跨度检查。站点经 uniquecode 关联 bsd_station;质控仅覆盖约23个站点。单站下钻(运行日志/曲线)走平台API工具 jiangsu_fetch_qc_*。'",
    ],
) }}

-- mart_qc_execution_analysis: 质控执行结果宽表
-- 一行 = 一条质控任务执行结果(站点×污染物×零点/跨度检查)。
-- 数据窗口: 2026-07-01 起(用户确认口径)。合格判定直接采用平台 result 文本,不重算。
-- 依赖: jiangsu_ods.qc_historyresult(5分钟增量) + dim_station 一致性维度(经 uniquecode 关联)。
select
    h.id                          as id,
    h.uniquecode                  as uniquecode,
    ds.station_code               as station_code,
    ds.station_name               as station_name,
    ds.city_code                  as city_code,
    ds.city_name                  as city_name,
    h.pollutant                   as pollutant,
    h.mission_name                as task_type,
    h.result                      as result_cn,
    (h.result = '合格')           as is_qualified,
    h.start_time                  as start_time,
    h.end_time                    as end_time,
    h.start_time::date            as qc_date,
    h.target_value                as target_value,
    h.relevant_value              as relevant_value,
    h.inaccuracy                  as inaccuracy,
    h.relative_error              as relative_error,
    h.rid                         as rid,
    h.create_time                 as source_create_time,
    now()::timestamp              as synced_at
from {{ source('jiangsu_ods', 'qc_historyresult') }} h
left join {{ ref('dim_station') }} ds
       on ds.uniquecode = h.uniquecode
