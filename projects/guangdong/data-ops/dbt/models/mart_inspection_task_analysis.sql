{{ config(
    indexes=[
        {'columns': ['task_item_id'], 'unique': True},
        {'columns': ['station_id']},
        {'columns': ['plan_date']},
        {'columns': ['is_finished']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_inspection_task_analysis 广东运维计划任务项分析宽表
-- 口径（2026-10-25 勘察确认）:
--   源   = PW_TASKITEM（一行 = 一个计划任务项）+ PW_TASK（任务头：规则/周期/站点）
--          两者按 PWTASKID 关联。PW_TASKITEM 每日按周期生成（今年约 8.3 万项）
--   完成 = FINISHDATETIME 非空（或 STATE=1）；完成可转工单（FINISHWORKORDERCODE）
--   超期 = 未完成且计划结束日期（EDTDATE）已过当前时间
--   表单 = RULEITEMTAG 指向 RF_W_* 表单实体（RF_W_GaseousCheck → RF_W_GASEOUSCHECK_*）
--   注意 = 任务项完成态滞后于创建（创建后在周期内完成），PW_TASKITEM 走
--          每日全量+今年创建窗口同步，增量水位不可用于完成率
-- 刷新: 全量重建（今年窗口，每日）
-- ============================================================
select
    i.pwtaskitemid                                  as task_item_id,
    i.pwtaskid                                      as task_id,
    t.stationid                                     as station_id,
    s.station_code                                  as station_code,
    s.station_name                                  as station_name,
    s.city_code                                     as city_code,
    s.city_name                                     as city_name,
    t.rulename                                      as rule_name,
    t.ruletype                                      as rule_type,
    t.rulecycle                                     as rule_cycle,
    i.ruleitemtag                                   as item_form_tag,
    i.pollutanttype                                 as pollutant_type,
    i.sdtdate                                       as plan_start_date,
    i.edtdate                                       as plan_end_date,
    i.basedate                                      as plan_date,
    i.createtime                                    as create_time,
    (i.finishdatetime is not null or i.state = 1)   as is_finished,
    i.finishdatetime                                as finish_datetime,
    i.finishuserid                                  as finish_user_id,
    (nullif(i.finishworkordercode, '') is not null) as is_to_order,
    i.finishworkordercode                           as finish_work_order_code,
    ((i.finishdatetime is null and i.state <> 1)
     and i.edtdate is not null and i.edtdate < current_date) as is_overdue,
    i.state                                         as state_code,
    now()::timestamp                                as refreshed_at
from {{ source('guangdong_ods', 'pw_taskitem') }} i
left join {{ source('guangdong_ods', 'pw_task') }} t
       on t.pwtaskid = i.pwtaskid
left join {{ ref('dim_station') }} s
       on s.station_id = t.stationid
