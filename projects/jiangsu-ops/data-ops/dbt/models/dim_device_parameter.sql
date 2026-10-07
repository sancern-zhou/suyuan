{{ config(
    indexes=[
        {'columns': ['devicemodel_id']},
        {'columns': ['parameterid']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '设备型号健康参数阈值维度表(每日全量,源自 jiangsu_ods.bsd_moniter_parameter)。一行=设备型号×受检参数的上下限/预警限;参数名为空的行已剔除(源库约37%)。诊断站点故障时按该站设备的 device_model_id 取参数核对清单(alm_rule 管污染指标告警阈值,本表管设备健康参数)。warntype=Range 为量程型(看上下限),State 为状态型(看是否正常)。'",
    ],
) }}

-- dim_device_parameter: 设备型号×健康参数阈值维度表。
-- 用途: station_fault_diagnosis——按站点设备(dim_device.device_model_id)取应检参数与正常范围,
--       结合监测曲线/巡检读数判断硬件参数越限; smart_inspection——按型号生成巡检参数核对表。
-- 口径: 源 devicemodel/parameterid 为数字型文本(428 行, (型号,参数) 粒度唯一);
--       devicemodel_id 为安全转数值(非数字置空); 参数名 trim; statusname 为空的行不进本表。
select
    p.btrim_devicemodel                       as devicemodel,
    nullif(p.btrim_devicemodel, '')::bigint   as devicemodel_id,
    p.parameterid,
    p.parameter_name,
    p.series,
    p.toplimit,
    p.lowlimit,
    p.warn_top_limit,
    p.warn_low_limit,
    p.unit,
    p.warntype,
    p.description,
    d.device_count                            as model_device_count,
    now()::timestamp                          as synced_at
from (
    select
        btrim(devicemodel)                    as btrim_devicemodel,
        btrim(parameterid)                    as parameterid,
        btrim(statusname)                     as parameter_name,
        btrim(series)                         as series,
        toplimit,
        lowlimit,
        warntoplimit                          as warn_top_limit,
        warnlowlimit                          as warn_low_limit,
        btrim(unit)                           as unit,
        btrim(warntype)                       as warntype,
        left(btrim("describe"), 500)          as description
    from {{ source('jiangsu_ods', 'bsd_moniter_parameter') }}
    where btrim(statusname) is not null
) p
left join (
    select devicemodelid, count(*) as device_count
    from {{ source('jiangsu_ods', 'bsd_device') }}
    group by devicemodelid
) d
    on d.devicemodelid::text = p.btrim_devicemodel
