{{ config(
    indexes=[
        {'columns': ['event_id'], 'unique': True},
        {'columns': ['device_id']},
        {'columns': ['station_id']},
        {'columns': ['event_time']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- ============================================================
-- mart_device_lifecycle_analysis 广东设备生命周期事件宽表
-- 口径（2026-10-25 勘察确认）:
--   源   = LOG_DEVICE（一行 = 一条设备状态/事件日志，今年约 7.4 万条）
--   事件 = EVENTSTATE 动作（WeekCheck=周检 / MonthCheck=月检 / QuaryCheck=季检 /
--          HYCheck=半年检 / YearCheck=年检 / DeviceStart=启用 / DeviceAdd=新增 /
--          DeviceStop=停用 / DeviceUpdata=信息更新，其余保留原文）
--   状态 = DEVICEIDSTATE 变更后状态（DeviceNormal/DeviceSpare 等，原文）
--   站点/设备 = STATIONID/DEVICEID 经 dim_station/dim_device 关联
-- 刷新: 全量重建（今年窗口，小时级）
-- ============================================================
select
    l.devicelogid                                   as event_id,
    l.deviceid                                      as device_id,
    dv.device_code                                  as device_code,
    dv.device_type                                  as device_type,
    l.stationid                                     as station_id,
    s.station_code                                  as station_code,
    s.station_name                                  as station_name,
    s.city_code                                     as city_code,
    s.city_name                                     as city_name,
    l.eventstate                                    as event_type,
    case l.eventstate
        when 'WeekCheck' then '周检'
        when 'MonthCheck' then '月检'
        when 'QuaryCheck' then '季检'
        when 'HYCheck' then '半年检'
        when 'YearCheck' then '年检'
        when 'DeviceStart' then '设备启用'
        when 'DeviceAdd' then '设备新增'
        when 'DeviceStop' then '设备停用'
        when 'DeviceUpdata' then '设备信息更新'
        else l.eventstate
    end                                             as event_type_cn,
    l.deviceidstate                                 as state_after,
    l."time"                                        as event_time,
    l.expecttime                                    as expect_time,
    l.orderid                                       as order_id,
    l.remarks                                       as remarks,
    now()::timestamp                                as refreshed_at
from {{ source('guangdong_ods', 'log_device') }} l
left join {{ ref('dim_device') }} dv
       on dv.device_id = l.deviceid
left join {{ ref('dim_station') }} s
       on s.station_id = l.stationid
