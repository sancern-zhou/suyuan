{{ config(
    indexes=[
        {'columns': ['devicelogid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- log_device：契约透传层（源 dbo.LOG_DEVICE，一行 = 一条原始记录）。
-- 契约: sync/datasets/log_device.yaml；列名与 ODS 一致（源列名小写）。
select
    devicelogid,
    deviceid,
    time,
    warehousename,
    userid,
    stationid,
    deviceidstate,
    eventstate,
    expecttime,
    remarks,
    orderid,
    url,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'log_device') }}
