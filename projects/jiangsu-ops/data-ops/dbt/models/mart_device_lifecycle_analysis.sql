{{ config(
    indexes=[
        {'columns': ['event_id'], 'unique': True},
        {'columns': ['device_id']},
        {'columns': ['station_code']},
        {'columns': ['event_time']},
        {'columns': ['state_after']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '设备生命周期事件流宽表(每日全量,窗口>=2026-07-01)。一行=一条设备生命周期事件:状态变更日志(log_device: 启用/故障/维修/备机/校准/停用等 deviceidstate×eventstate 流转,可关联故障工单)∪报废审批(dev_scrap, event_source=dev_scrap, 带 scrap_reason)。备机更换及时性等设备周期分析查此表;state_after/event_type 为平台原始枚举未翻译。'",
    ],
) }}

-- mart_device_lifecycle_analysis: 设备生命周期事件流(状态变更日志 ∪ 报废审批)。
-- 用途: 设备周期分析(最近启用/故障/维修轨迹/备机事件 DeviceSpare/停用/报废)、
--       备机更换及时性(同站 DeviceSpare 流转)、事件与故障工单关联(working_order_code)。
-- 口径: 状态枚举沿用平台原文(DeviceFault/DeviceNormal/DeviceSpare/NoCalibration/DeviceStopRun/DeviceDelete
--       × DeviceRepair/DeviceStart/Other/DeviceRemote/DeviceStop/DeviceCalibration/DeviceRemove/DeviceReturn);
--       报废行 event_source='dev_scrap', state_after/event_type 为空, scrap_reason 为报废理由。
--       station_code 优先取事件自带站点码, 缺失回退设备台账归属站点; 时间窗口 ≥2026-07-01 仅覆盖日志, 报废为全量。
select
    l.event_id,
    l.event_source,
    l.event_time,
    l.device_id,
    d.devicecode                              as device_code,
    coalesce(l.event_station, d.stationcode)  as station_code,
    ds.station_name,
    ds.city_code,
    ds.city_name,
    d.devicetype                              as device_type,
    bt.name                                   as device_type_name,
    d.devicemodelid                           as device_model_id,
    l.state_after,
    l.event_type,
    nullif(btrim(l.remarks), '')              as remarks,
    nullif(btrim(l.working_order_code), '')   as working_order_code,
    l.scrap_reason,
    l.approve_result,
    now()::timestamp                          as synced_at
from (
    select
        'log_' || cast(id as text)            as event_id,
        'log_device'                          as event_source,
        timepoint                             as event_time,
        deviceid                              as device_id,
        stationcode                           as event_station,
        deviceidstate                         as state_after,
        eventstate                            as event_type,
        left(remarks, 500)                    as remarks,
        left(workingordercode, 40)            as working_order_code,
        null::text                            as scrap_reason,
        null::boolean                         as approve_result
    from {{ source('jiangsu_ods', 'log_device') }}
    union all
    select
        'scrap_' || cast(id as text),
        'dev_scrap',
        coalesce(APPROVETIME, APPLYTIME),
        DEVICEID,
        null,
        null,
        null,
        null,
        null,
        btrim(SCRAPREASON),
        APPROVERESULT
    from {{ source('jiangsu_ods', 'dev_scrap') }}
) l
left join {{ source('jiangsu_ods', 'bsd_device') }} d
       on d.id = l.device_id
left join {{ ref('dim_station') }} ds
       on ds.station_code = coalesce(l.event_station, d.stationcode)
left join {{ source('jiangsu_ods', 'bsd_devicetype') }} bt
       on bt.code = d.devicetype
