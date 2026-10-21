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
        "COMMENT ON TABLE {{ this }} IS '质控执行结果宽表(2026-06-01起,站点名录省控站口径)。result_cn 为平台原始判定文本(合格/不合格/任务失败/终止等);is_qualified: 前缀合格→true、前缀不合格→false、其余(任务失败/终止/校准类)为NULL不计入合格率分母。范围=源库名录 stationtypeid=2 且启用的省控站(2026-10-14 起为101个);超站(7099A)与40开头试点站不在范围。单站下钻走平台API工具 jiangsu_fetch_qc_*。'",
    ],
) }}

-- mart_qc_execution_analysis: 质控执行结果宽表(省控站口径)
-- 一行 = 一条质控任务执行结果(站点×污染物×检查/校准类型)。
-- 源: air_province_data.dbo.qc_his_result_2026(平台质控任务结果,按年分表;每年1月需新增当年分表同步配置)。
-- 范围: 同步层按源库名录过滤(stationtypeid=2 AND status=1,当前101个启用省控站;超站7099A、
--       40开头质控仪试点站、停用省控站均不同步),模型层再经 dim_station 关联 station_type_id=2 兜底。
-- 合格判定: 直接采用平台 qcresult 文本前缀,不重算阈值。
-- 旧源 qc_historyresult 自2023-09起仅剩40开头试点站自动核查,2026-10-14 起退役不再同步。
select
    h.id                          as id,
    h.uniquecode                  as uniquecode,
    ds.station_code               as station_code,
    ds.station_name               as station_name,
    ds.city_code                  as city_code,
    ds.city_name                  as city_name,
    h.poll                        as pollutant,
    h.qctype                      as task_type,
    h.qcresult                    as result_cn,
    case
        when h.qcresult like '合格%'   then true
        when h.qcresult like '不合格%' then false
    end                           as is_qualified,
    coalesce(h.rstart, h.sstart, h.createtime) as start_time,
    h.endtime                     as end_time,
    coalesce(h.rstart, h.sstart, h.createtime)::date as qc_date,
    nullif(h.tvalue, '')::numeric as target_value,
    nullif(h.rvalue, '')::numeric as relevant_value,
    nullif(h.inac, '')::numeric   as inaccuracy,
    h.relativeerror               as relative_error,
    h.rid                         as rid,
    h.createtime                  as source_create_time,
    now()::timestamp              as synced_at
from {{ source('jiangsu_ods', 'qc_his_result_2026') }} h
join {{ ref('dim_station') }} ds
  on ds.uniquecode = h.uniquecode
where ds.station_type_id = 2
  -- 平台曾把年中前的历史执行补灌进年度表(高id携带更早createtime), id窗口种子会带入
  -- 2026-04起的记录; 显式按执行日截窗, 与全局"数据自2026-06-01起"口径保持一致
  and coalesce(h.rstart, h.sstart, h.createtime) >= timestamp '2026-06-01'
