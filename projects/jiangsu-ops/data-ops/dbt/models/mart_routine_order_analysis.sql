{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['create_time']},
        {'columns': ['order_type']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '例行单分析宽表(非故障工单全集:巡检/校准/补录/质控,一行=一张单)。task_item_* 聚合来自 mtc_taskitem(status 0=未开始/1=已完成);is_form_only_close=流程闭环但所有任务项未填报(内容空白即闭环,2026-11-03 如东芳泉路CH261026型)。工单存在性/全类型清单的权威口径;故障单统计另见 mart_work_order_analysis,巡检任务项完成台账另见 mart_inspection_analysis。'",
    ],
) }}

-- mart_routine_order_analysis: 例行单(非故障工单)分析宽表
-- 一行 = 一张例行单(mtc_WorkingOrder.ordertype <> 'Fault')。背景: 2026-11-03 问数假阴性
-- 事故(按工单号查不到 → 误答"没有工单")暴露例行单没有 Agent 可查的统计口径,
-- 本表把"建单率/填报率/形式闭环但内容空白"做成可查指标。
-- 任务项聚合: mtc_taskitem.status 实测只有 0(未开始)/1(已完成)两态;
-- 逐项进度明细仍走 jiangsu_ods.mtc_taskitem 原始行(已在 ODS 兜底白名单)。
with items as (
    select workingordercode,
           count(*)                              as task_item_count,
           count(*) filter (where status = 1)    as task_items_finished,
           count(*) filter (where status = 0)    as task_items_unstarted
    from {{ source('jiangsu_ods', 'mtc_taskitem') }}
    group by 1
),
nodes as (
    select workingordercode, count(*) as node_count
    from {{ source('jiangsu_ods', 'mtc_working_order_detail') }}
    group by 1
)
select
    w.id                          as id,
    w.workingordercode            as working_order_code,
    w.ordertype                   as order_type,
    case w.ordertype
        when 'Check' then '巡检/现场检查'
        when 'Calibration' then '仪器校准'
        when 'DataEntry' then '数据补录'
        when 'QC' then '质控例行'
        when 'QA' then '质控审核'
        else '其他' end            as order_type_cn,
    w.ordercreatetype             as order_create_type,
    case w.ordercreatetype
        when 'Plan' then '平台按计划自动生成'
        when 'Manual' then '人工创建'
        else w.ordercreatetype end as order_create_type_cn,
    w.ruletype                    as rule_type,
    case w.ruletype
        when 'Week' then '周检'
        when 'Month' then '月检'
        when 'Quarter' then '季检'
        when 'HalfYear' then '半年检'
        when 'Year' then '年检'
        else '无周期' end          as rule_type_cn,
    w.ordertitle                  as order_title,
    w.orderstatus                 as order_status,
    case w.orderstatus
        when 'Finish' then '已完成'
        when 'Doing' then '处理中'
        when 'Wait' then '等待中'
        when 'Invalid' then '已作废'
        else w.orderstatus end     as order_status_cn,
    w.workflowstatus              as workflow_status,
    case w.workflowstatus
        when 'Finish' then '已闭环'
        when 'Doing' then '流转中'
        when 'ToAssign' then '待分派'
        else w.workflowstatus end  as workflow_status_cn,
    w.urgencytype                 as urgency_type,
    w.stationcode                 as station_code,
    ds.station_name               as station_name,
    ds.station_type_name          as station_type_name,
    ds.city_code                  as city_code,
    ds.city_name                  as city_name,
    w.deviceid                    as device_id,
    w.operationunitid             as operation_unit_id,
    w.createtime                  as create_time,
    w.createusername              as create_user_name,
    w.planfinishtime              as plan_finish_time,
    w.finishtime                  as finish_time,
    (w.finishtime is not null and w.planfinishtime is not null
        and w.finishtime::date > w.planfinishtime::date) as finished_after_plan,
    (w.orderstatus not in ('Finish', 'Invalid')
        and w.planfinishtime is not null
        and w.planfinishtime < current_date)               as is_overdue,
    w.currentpoint                as current_point,
    n.node_count                  as node_count,
    i.task_item_count             as task_item_count,
    i.task_items_finished         as task_items_finished,
    i.task_items_unstarted        as task_items_unstarted,
    (coalesce(i.task_items_finished, 0) > 0)               as is_content_filled,
    (w.workflowstatus = 'Finish'
        and w.orderstatus <> 'Invalid'
        and coalesce(i.task_items_finished, 0) = 0)        as is_form_only_close,
    w.updatetime                  as source_updated_at,
    now()::timestamp              as refreshed_at
from {{ source('jiangsu_ods', 'mtc_working_order') }} w
left join items i on i.workingordercode = w.workingordercode
left join nodes n on n.workingordercode = w.workingordercode
left join {{ ref('dim_station') }} ds on ds.station_code = w.stationcode
where w.ordertype <> 'Fault'
