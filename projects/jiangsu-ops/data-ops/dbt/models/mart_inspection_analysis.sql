{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['task_date']},
        {'columns': ['city_code']},
        {'columns': ['is_finished']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '巡检完成宽表(2026-07-01起,一行=一条巡检任务项)。status_cn 按数据分布推断(0=未开始/1=处理中/2=已完成,待业务确认);is_overdue=计划周期已结束仍未完成;has_linked_order 标记巡检转工单。'",
    ],
) }}

-- mart_inspection_analysis: 巡检完成宽表
-- 一行 = 一条巡检任务项(pw_TaskItem)。数据窗口: 2026-07-01 起(UpdateTime 引导)。
-- 维度经 dim_station(uniquecode 关联);周期窗口/超期判定经 pw_Task(每日全量)。
-- 口径注意: status 0/1/2 按数据分布推断为 未开始/处理中/已完成(待业务确认);
--           is_overdue = 计划周期已结束且未完成。
select
    i.id                     as id,
    i.uniquecode             as uniquecode,
    ds.station_code          as station_code,
    ds.station_name          as station_name,
    ds.city_code             as city_code,
    ds.city_name             as city_name,
    i.ruletype               as ruletype,
    case i.ruletype
        when 'Week' then '周巡检'
        when 'Month' then '月巡检'
        when 'Quarter' then '季巡检'
        when 'HalfYear' then '半年巡检'
        when 'Year' then '年巡检'
        else '其他' end      as rule_type_cn,
    i.pollutanttype          as pollutanttype,
    i.taskusername           as taskusername,
    i.status                 as status,
    case i.status
        when 2 then '已完成'
        when 1 then '处理中'
        when 0 then '未开始'
        else '未知' end      as status_cn,
    (i.status = 2)           as is_finished,
    i.workingordercode       as workingordercode,
    (coalesce(i.workingordercode, '') <> '') as has_linked_order,
    i.taskdate               as task_date,
    i.createtime             as createtime,
    i.finishtime             as finishtime,
    t.sdtedate               as plan_start_date,
    t.edtedate               as plan_end_date,
    (t.edtedate is not null and i.status <> 2 and t.edtedate < current_date) as is_overdue,
    now()::timestamp         as synced_at
from {{ source('jiangsu_ods', 'pw_taskitem') }} i
left join {{ source('jiangsu_ods', 'pw_task') }} t
       on t.taskid = i.pwtaskid
left join {{ ref('dim_station') }} ds
       on ds.uniquecode = i.uniquecode
