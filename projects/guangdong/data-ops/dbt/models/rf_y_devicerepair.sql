{{ config(
    indexes=[
        {'columns': ['rfydevicerepairid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_y_devicerepair：契约透传层（源 dbo.RF_Y_DEVICEREPAIR，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_y_devicerepair.yaml；列名与 ODS 一致（源列名小写）。
select
    rfydevicerepairid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    devicemodel,
    repairtime,
    backtime,
    repairphenomenon,
    repairprocess,
    devicename,
    slope,
    intercept,
    coefficientr,
    zerodrift,
    spandrift,
    zerodriftsatisfy,
    spandriftsatisfy,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    processtype,
    zerodrift2,
    spandrift2,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_y_devicerepair') }}
