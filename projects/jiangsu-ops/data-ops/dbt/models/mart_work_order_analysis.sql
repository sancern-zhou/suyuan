{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['city_code']},
        {'columns': ['create_time']},
        {'columns': ['order_status']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_work_order_analysis 江苏故障工单分析数据集（阶段一打样）
-- 口径（2026-09-21 业务确认; SLA 2026-09-22 业务确认）:
--   响应时长 = 派单→到站; 代理: 派单=CH_Check 节点开始, 到站=首个 FaultProcess 开始
--             派单缺失回退 CreateTime (contract 中标注 fallback)
--             注: 当前流程数据中 CH_Check 与 FaultProcess 不同时出现,
--             实际响应代理 = 创建→到站, 仅对有到场节点(约14%)的工单可评估
--   2小时响应  = is_response_within_2h: 响应时长<=120分钟(仅到场单可评估)
--   4小时处置  = 数据恢复正常(业务确认 2026-09-22); 代理 = 同站告警解除时间
--             (alm_summary.removetime, 平台规则判定, 断数/恒值/超标类统一适用),
--             取建单前1小时至后7天内、解除时间在建单之后的最早告警解除;
--             is_recover_within_4h: 恢复距建单<=4小时(无关联告警解除则不可评估)
--   超期     = FinishTime>PlanFinishTime; 未完成且 now()>PlanFinishTime 亦为超期; Invalid 不计
--   重复故障 = 同站同设备, 本单创建前 30 天内存在其他工单
-- 范围     = 仅故障工单(ordertype='Fault'); 例行单不入本表(2026-10-06 收敛, 见文末 where)
-- 关联告警 = 工单创建前 24h 内同站 alm_summary 条数（代理口径）
-- 刷新: 全量重建（数据量 <2 万行, 5 分钟一次成本可忽略）
-- ============================================================
select
    w.id                                                        as id,
    w.workingordercode                                          as working_order_code,
    w.ordertitle                                                as order_title,
    w.ordertype                                                 as order_type,
    w.orderstatus                                               as order_status,
    case w.orderstatus
        when 'Doing' then '处理中'
        when 'Finish' then '已完成'
        when 'Invalid' then '已作废'
        else w.orderstatus
    end                                                         as order_status_cn,
    w.urgencytype                                               as urgency_type,
    w.stationcode                                               as station_code,
    s.positionname                                              as station_name,
    s.areacode                                                  as city_code,
    c.name                                                      as city_name,
    nullif(w.deviceid, 0)                                       as device_id,
    w.operationunitid                                           as operation_unit_id,
    w.createtime                                                as create_time,
    d.dispatch_time                                             as dispatch_time,
    d.arrival_time                                              as arrival_time,
    w.finishtime                                                as finish_time,
    w.planfinishtime                                            as plan_finish_time,
    w.currentpoint                                              as current_point,
    coalesce(n.node_count, 0)                                   as node_count,
    case when d.arrival_time is not null
         then round(extract(epoch from (d.arrival_time - coalesce(d.dispatch_time, w.createtime))) / 60.0, 1)
    end                                                         as response_minutes,
    case when d.arrival_time is not null and w.finishtime is not null
         then round(extract(epoch from (w.finishtime - d.arrival_time)) / 60.0, 1)
    end                                                         as process_minutes,
    case when w.finishtime is not null
         then round(extract(epoch from (w.finishtime - w.createtime)) / 60.0, 1)
    end                                                         as repair_minutes,
    (d.arrival_time is not null
     and extract(epoch from (d.arrival_time - coalesce(d.dispatch_time, w.createtime))) <= 7200)
                                                                as is_response_within_2h,
    rc.trigger_alarm_time                                       as trigger_alarm_time,
    rc.recovery_time                                            as recovery_time,
    case when rc.recovery_time is not null
         then round(extract(epoch from (rc.recovery_time - rc.trigger_alarm_time)) / 3600.0, 1)
    end                                                         as recovery_hours,
    (rc.recovery_time is not null
     and extract(epoch from (rc.recovery_time - rc.trigger_alarm_time)) <= 14400)
                                                                as is_recover_within_4h,
    ((w.finishtime is not null and w.planfinishtime is not null and w.finishtime > w.planfinishtime)
     or (w.finishtime is null and w.planfinishtime is not null
         and w.orderstatus <> 'Invalid' and now() > w.planfinishtime))
                                                                as is_overdue,
    coalesce(rp.repeat_count_30d, 0) > 0                        as is_repeat_fault,
    case when nullif(w.deviceid, 0) is not null then '站点+设备'
         when w.stationcode is not null and w.stationcode <> '' then '仅站点(工单未填设备)'
    end                                                         as repeat_fault_basis,
    coalesce(rp.repeat_count_30d, 0)                            as repeat_count_30d,
    coalesce(al.alarm_count, 0)                                 as alarm_count_1d,
    w.updatetime                                                as source_updated_at,
    now()::timestamp                                            as refreshed_at
from {{ source('jiangsu_ods', 'mtc_working_order') }} w
left join {{ source('jiangsu_ods', 'bsd_station') }} s
       on s.stationcode = w.stationcode
left join {{ source('jiangsu_ods', 'bsd_city') }} c
       on c.code = case when length(s.areacode) >= 4
                        then rpad(left(s.areacode, 4), 6, '0')
                        else s.areacode end
      and c.level = '2'
left join (
    select workingordercode,
           min(case when processstep = 'CH_Check' then processsdttime end) as dispatch_time,
           min(case when processstep = 'FaultProcess' then processsdttime end) as arrival_time
    from {{ source('jiangsu_ods', 'mtc_working_order_detail') }}
    group by workingordercode
) d on d.workingordercode = w.workingordercode
left join (
    select workingordercode, count(*) as node_count
    from {{ source('jiangsu_ods', 'mtc_working_order_detail') }}
    group by workingordercode
) n on n.workingordercode = w.workingordercode
left join (
    select w2.id,
           count(*) over (partition by w2.stationcode, nullif(w2.deviceid, 0)
                          order by w2.createtime
                          range between interval '30 days' preceding
                                    and interval '1 microsecond' preceding) as repeat_count_30d
    from {{ source('jiangsu_ods', 'mtc_working_order') }} w2
    where w2.orderstatus <> 'Invalid'
) rp on rp.id = w.id
left join lateral (
    select count(*) as alarm_count
    from {{ source('jiangsu_ods', 'alm_summary') }} a
    where a.stacode = w.stationcode
      and a.alarmtime between w.createtime - interval '24 hours' and w.createtime
) al on true
left join lateral (
    -- 4小时处置(数据恢复正常)代理: 触发告警的解除时间(平台规则判定)。
    -- 关联 = 建单前24h~后1h内同站最近一条已解除告警; 恢复耗时从告警发生起算。
    select a.alarmtime  as trigger_alarm_time,
           a.removetime as recovery_time
    from {{ source('jiangsu_ods', 'alm_summary') }} a
    where a.stacode = w.stationcode
      and a.alarmtime between w.createtime - interval '24 hours' and w.createtime + interval '1 hour'
      and a.removetime is not null
    order by a.alarmtime desc
    limit 1
) rc on true
-- 范围(2026-10-06): 仅故障工单(ordertype='Fault')。例行单(巡检/现场检查/校准/质控等)
-- 与故障单同存于源表 mtc_WorkingOrder, 但响应/恢复/重复故障指标均以故障单节点为前提,
-- 例行单不入本表; 例行巡检任务项见 mart_inspection_analysis。
where w.ordertype = 'Fault'
  and (w.orderstatus <> 'Invalid' or w.finishtime is not null)
