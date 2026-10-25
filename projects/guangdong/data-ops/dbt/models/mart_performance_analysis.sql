{{ config(
    indexes=[
        {'columns': ['ospsid'], 'unique': True},
        {'columns': ['station_id']},
        {'columns': ['performance_month']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_performance_analysis 广东站点绩效月度考核宽表
-- 口径（2026-10-25 勘察确认）:
--   源   = OPA_STATIONPERFORMANCESCORE（一行 = 一个站点×月的绩效考核记录，
--          平台每日 10:15 左右重算，updatedate 刷新）
--   得分 = totalscore(总分)/tworatescore(两率)/qualitycontrolscore(质控)/
--          effectrate(有效率)/provincecenterscore(省中心) 均为平台考核口径原值，不重算
--   金额 = initialamount(合同金额)/htje(合同额核减)/kkje(扣款金额)/sjje(实发金额)，单位元
--   质控 = qcnumber/allqcnumber(质控次数)/qcqualifiedrate(合格率)
--   站点 = stationid 经 dim_station（主网+组分网 432 站）
--   范围 = 2026 合同年度（GDEEMC-2026 系列合同，sdt 2026-01-01 起）
-- 刷新: 全量重建（1.3 万行，每日）
-- ============================================================
select
    s.ospsid                                          as ospsid,
    s.stationid                                       as station_id,
    d.station_code                                    as station_code,
    d.station_name                                    as station_name,
    d.city_code                                       as city_code,
    d.city_name                                       as city_name,
    d.station_type_name                               as station_type_name,
    d.operation_unit_name                             as operation_unit_name,
    s.performancemouth                                as performance_month,
    s.projectname                                     as project_name,
    s.contractname                                    as contract_name,
    s.contractcode                                    as contract_code,
    s.sdt                                             as contract_start_date,
    s.edt                                             as contract_end_date,
    s.totalscore                                      as total_score,
    s.tworatescore                                    as two_rate_score,
    s.qualitycontrolscore                             as quality_control_score,
    s.effectrate                                      as effect_rate,
    s.effectratescore                                 as effect_rate_score,
    s.provincecenterscore                             as province_center_score,
    s.acquisitionratio                                as acquisition_ratio,
    s.qcnumber                                        as qc_number,
    s.allqcnumber                                     as all_qc_number,
    s.qcqualifiedrate                                 as qc_qualified_rate,
    s.initialamount                                   as initial_amount,
    s.htje                                            as deduction_amount,
    s.kkje                                            as penalty_amount,
    s.sjje                                            as paid_amount,
    s.status                                          as status_code,
    s.archivingdate                                   as archiving_date,
    s.deductionremark                                 as deduction_remark,
    s.createdate                                      as source_created_at,
    s.updatedate                                      as source_updated_at,
    now()::timestamp                                  as refreshed_at
from {{ source('guangdong_ods', 'opa_stationperformancescore') }} s
left join {{ ref('dim_station') }} d
       on d.station_id = s.stationid
