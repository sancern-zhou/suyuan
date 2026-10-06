{{ config(
    indexes=[
        {'columns': ['station_code']},
        {'columns': ['device_code']},
        {'columns': ['device_type']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '站点设备台账维度表(每日全量,源自 jiangsu_ods.bsd_device)。device_stats 为平台设备状态码(原始枚举,未翻译);device_type_name 为设备类型名(bsd_DeviceType 字典);生命周期事件流见 mart_device_lifecycle_analysis。'",
    ],
) }}

-- dim_device: 站点设备台账维度表（来自 jiangsu_ods.bsd_device，每日全量）。
-- 用途：Agent 常规台账查询（设备构成/品牌型号/购置启用日期/状态），
-- 替代已下线的 jiangsu_fetch_device_ledger 接口工具的公共部分。
-- 口径说明：台账为"当前挂载快照"；启用/故障/备机/报废等生命周期事件流
-- 查 mart_device_lifecycle_analysis（源自 log_device+dev_scrap，2026-10 接入）。
select
    d.id,
    d.devicecode                       as device_code,
    d.stationcode                      as station_code,
    d.assetscode                       as assets_code,
    d.address,
    d.devicetype                       as device_type,
    bt.name                            as device_type_name,
    d.devicebrand                      as device_brand,
    d.devicemodel                      as device_model,
    d.devicemodelid                    as device_model_id,
    d.calibrate,
    d.purchasedate                     as purchase_date,
    d.usedate                          as use_date,
    d.batchno                          as batch_no,
    d.qualityperiod                    as quality_period,
    d.manufactor,
    d.custodian,
    d.maintercompany                   as mainter_company,
    d.createtime                       as create_time,
    d.originalmachine                  as original_machine,
    d.masterslavenum                   as master_slave_num,
    d.devicestats                      as device_stats,
    d.warehouse,
    d.price,
    d.source,
    d.sourcename                       as source_name,
    d.assetownership                   as asset_ownership,
    now()::timestamp                   as synced_at
from {{ source('jiangsu_ods', 'bsd_device') }} d
left join {{ source('jiangsu_ods', 'bsd_devicetype') }} bt
       on bt.code = d.devicetype
