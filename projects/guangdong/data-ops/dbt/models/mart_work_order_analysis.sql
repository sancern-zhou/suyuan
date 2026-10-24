{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['working_order_code']},
        {'columns': ['station_code']},
        {'columns': ['create_time']},
        {'columns': ['order_type']},
        {'columns': ['order_status']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_work_order_analysis 广东运维工单分析宽表
-- 口径（对齐 docs/work-order-semantics/ 语义字典与江苏 mart 模式）:
--   范围     = 全类型工单（含作废 Invalid）；工单量/时效结论必须按 order_status/order_type 过滤
--   超期     = FinishTime>PlanFinishTime; 未完成且 now()>PlanFinishTime 亦为超期; Invalid 不计
--              与江苏不同: 广东工单有计划完成时间, 超期可评估;
--              分母 overdue_evaluable = plan_finish_time 非空 (部分类型无计划时间)
--   到站     = 首个 FaultProcess 步骤开始时间 (仅故障处理流程有该节点);
--              响应时长 = 到站 - 创建; 2小时响应 = 响应时长 <= 120 分钟
--   重复故障 = 同站同设备, 本单创建前 30 天内存在其他故障单(Fault/SupFault);
--              仅故障单口径有意义, 非故障单恒 0/false
--   附件     = wo_commonfile_links 按 working_order_code 计数 (仅索引, 本体在源系统)
--   站点/设备维度经 dim_station/dim_device 宽表化; 城市维度暂缺(仅 region_id)
-- 刷新: 全量重建（工单量十万级以内, 每小时成本可忽略）
-- ============================================================
with details as (
    select
        working_order_code,
        min(process_start_time)                                             as first_step_time,
        min(case when process_step = 'FaultProcess'
                 then process_start_time end)                               as arrival_time,
        count(*)                                                            as node_count
    from {{ source('guangdong_ods', 'working_order_details') }}
    group by working_order_code
),
first_fault_reason as (
    select distinct on (working_order_code)
        working_order_code,
        alarm_reason
    from {{ source('guangdong_ods', 'working_order_details') }}
    where process_step = 'FaultProcess'
      and nullif(trim(coalesce(alarm_reason, '')), '') is not null
    order by working_order_code, process_start_time, id
),
attachments as (
    select
        working_order_code,
        count(*) as attachment_count
    from {{ source('guangdong_ods', 'wo_commonfile_links') }}
    group by working_order_code
),
repeat_counts as (
    -- 30天重复故障回看: 仅统计故障单(Fault/SupFault), 同站同设备;
    -- RANGE 窗口按 create_time 排序, 计本单创建时刻之前(不含本单)30天内的同维度单数
    select
        id,
        repeat_count_30d
    from (
        select
            id,
            count(*) over w30 as repeat_count_30d
        from {{ source('guangdong_ods', 'working_orders') }}
        where order_type in ('Fault', 'SupFault')
          and station_id is not null and device_id is not null
        window w30 as (
            partition by station_id, device_id
            order by create_time
            range between interval '30 days' preceding and interval '1 second' preceding
        )
    ) x
)
select
    w.id                                                        as id,
    w.working_order_code                                        as working_order_code,
    w.order_title                                               as order_title,
    w.order_type                                                as order_type,
    w.order_status                                              as order_status,
    case w.order_status
        when 'Finish' then '已完成'
        when 'Doing' then '处理中'
        when 'Wait' then '待处理'
        when 'Invalid' then '已作废'
        else w.order_status
    end                                                         as order_status_cn,
    w.urgency_type                                              as urgency_type,
    w.maintenance_type                                          as maintenance_type,
    w.station_id                                                as station_id,
    d.station_code                                              as station_code,
    d.station_name                                              as station_name,
    d.station_type                                              as station_type,
    d.station_type_name                                         as station_type_name,
    d.city_code                                                 as city_code,
    d.city_name                                                 as city_name,
    d.region_id                                                 as region_id,
    w.device_id                                                 as device_id,
    dv.device_code                                              as device_code,
    dv.device_type                                              as device_type,
    w.create_time                                               as create_time,
    w.update_time                                               as update_time,
    w.finish_time                                               as finish_time,
    w.plan_finish_time                                          as plan_finish_time,
    w.current_workflow_point                                    as current_workflow_point,
    coalesce(dd.node_count, 0)                                  as node_count,
    dd.first_step_time                                          as first_step_time,
    dd.arrival_time                                             as arrival_time,
    case when dd.arrival_time is not null
         then round(extract(epoch from (dd.arrival_time - w.create_time)) / 60.0, 1)
    end                                                         as response_minutes,
    case when dd.arrival_time is not null and w.finish_time is not null
         then round(extract(epoch from (w.finish_time - dd.arrival_time)) / 60.0, 1)
    end                                                         as process_minutes,
    case when w.finish_time is not null
         then round(extract(epoch from (w.finish_time - w.create_time)) / 60.0, 1)
    end                                                         as repair_minutes,
    (dd.arrival_time is not null
     and extract(epoch from (dd.arrival_time - w.create_time)) <= 7200)
                                                                as is_response_within_2h,
    (w.order_status = 'Finish')                                 as is_finish,
    ((w.finish_time is not null and w.plan_finish_time is not null and w.finish_time > w.plan_finish_time)
     or (w.finish_time is null and w.plan_finish_time is not null
         and w.order_status <> 'Invalid' and now() > w.plan_finish_time))
                                                                as is_overdue,
    (w.plan_finish_time is not null)                            as overdue_evaluable,
    coalesce(rp.repeat_count_30d, 0) > 0                        as is_repeat_fault,
    coalesce(rp.repeat_count_30d, 0)                            as repeat_count_30d,
    fr.alarm_reason                                             as first_alarm_reason,
    coalesce(at_.attachment_count, 0)                           as attachment_count,
    coalesce(at_.attachment_count, 0) > 0                       as has_attachment,
    w.total_expense                                             as total_expense,
    w.order_overtime                                            as order_overtime,
    w.total_overtime                                            as total_overtime,
    w.update_time                                               as source_updated_at,
    now()::timestamp                                            as refreshed_at
from {{ source('guangdong_ods', 'working_orders') }} w
left join {{ ref('dim_station') }} d
       on d.station_id = w.station_id
left join {{ ref('dim_device') }} dv
       on dv.device_id = w.device_id
left join details dd
       on dd.working_order_code = w.working_order_code
left join first_fault_reason fr
       on fr.working_order_code = w.working_order_code
left join attachments at_
       on at_.working_order_code = w.working_order_code
left join repeat_counts rp
       on rp.id = w.id
