{{ config(
    indexes=[
        {'columns': ['rfydevicechangeid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_y_devicechange：契约透传层（源 dbo.RF_Y_DEVICECHANGE，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_y_devicechange.yaml；列名与 ODS 一致（源列名小写）。
select
    rfydevicechangeid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    project,
    devicemodel1,
    devicemodel2,
    installtime,
    changetime,
    failurecause,
    condition,
    exchangetime,
    zerocheck,
    spancheck,
    flowcheck,
    calibration,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    processtype,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_y_devicechange') }}
