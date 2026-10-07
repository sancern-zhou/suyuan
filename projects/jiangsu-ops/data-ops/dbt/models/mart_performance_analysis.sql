{{ config(
    indexes=[
        {'columns': ['perf_month']},
        {'columns': ['station_code']},
        {'columns': ['city_code']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '站点月度考核宽表(2026-07起,一行=站点×月,FULL OUTER 合并两率与评分两表)。-99占位清洗为NULL;is_settled 仅反映两率是否出数(validdays>0),tworate 缺行月份(如2026-07/08,源库即如此)该列为false但 qaqc 评分列可能仍有值;qaqc 评分月中常为满分模板占位,结算后变化。'",
    ],
) }}

-- mart_performance_analysis: 站点月度考核宽表
-- 一行 = 站点×月;opa_performance_tworate(两率)与 opa_performance_qaqc(三项评分)
-- 按站点+月份 FULL OUTER 合成一张表(两表月份覆盖不同:tworate 缺 2026-07/08 行,源库即如此)。
-- 口径: -99/-99.00 = 当月未出数/未结算,一律清洗为 NULL;validdays 缺失或=0 视为两率未结算。
select
    t.id                                          as tworate_id,
    q.id                                          as qaqc_id,
    date_trunc('month', coalesce(t.timepoint, q.timepoint))::date as perf_month,
    coalesce(t.stationcode, q.stationcode)        as station_code,
    coalesce(t.stationname, q.stationname)        as station_name,
    ds.city_code                                  as city_code,
    ds.city_name                                  as city_name,
    coalesce(t.departmentname, q.departmentname)  as operation_unit,
    t.validdays                                   as validdays,
    (coalesce(t.validdays, 0) > 0)                as is_settled,
    nullif(t.deviceworkingrate, -99)              as device_working_rate,
    t.deviceworkingdescription                    as deviceworkingdescription,
    nullif(t.dataaccuracyrate, -99)               as data_accuracy_rate,
    t.dataaccuracydescription                     as dataaccuracydescription,
    nullif(q.dailyoperationscore, -99)            as daily_operation_score,
    nullif(q.qaqcscore, -99)                      as qaqc_score,
    nullif(q.archivesandmanagescore, -99)         as archive_score,
    nullif(q.score, -99)                          as total_score,
    now()::timestamp                              as synced_at
from {{ source('jiangsu_ods', 'opa_performance_tworate') }} t
full outer join {{ source('jiangsu_ods', 'opa_performance_qaqc') }} q
       on q.stationcode = t.stationcode
      and date_trunc('month', q.timepoint) = date_trunc('month', t.timepoint)
left join {{ ref('dim_station') }} ds
       on ds.station_code = coalesce(t.stationcode, q.stationcode)
where coalesce(t.timepoint, q.timepoint) >= '2026-07-01'
