{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- sup_devicedaycheck：契约透传层（源 dbo.Sup_DeviceDayCheck，一行 = 一条原始记录）。
-- 契约: sync/datasets/sup_devicedaycheck.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    stationid,
    stationname,
    cityname,
    provincename,
    contractid,
    contractname,
    packagenum,
    did,
    deviceid,
    devicetypename,
    devicebrandname,
    devicemodel,
    devicecode,
    operationunitname,
    timepoint,
    status,
    remark,
    datatype,
    createuserid,
    createtime,
    updateuserid,
    updatetime,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'sup_devicedaycheck') }}
