{{ config(
    indexes=[
        {'columns': ['device_id'], 'unique': True},
        {'columns': ['device_code']},
        {'columns': ['station_id']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- dim_device 设备台账维度（一行 = 一台登记设备）。
-- 源: guangdong_ods.base_device（dbo.base_device，每日全量）。
-- 契约: sync/datasets/dim_device.yaml（ID 输出为文本形式，工单表直接等值关联）。
select
    deviceid::text           as device_id,
    trim(devicecode)         as device_code,
    nullif(trim(devicetype), '')    as device_type,
    nullif(trim(devicebrand), '')   as device_brand,
    nullif(trim(devicemodel), '')   as device_model,
    stationid::text          as station_id,
    nullif(trim(deviceidstate), '') as device_id_state,
    pollutantid::text        as pollutant_id,
    enabletime               as enable_time,
    activationtime           as activation_time,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'base_device') }}
