{{ config(
    indexes=[
        {'columns': ['rfwotherdevicecheckid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_w_otherdevicecheck：契约透传层（源 dbo.RF_W_OTHERDEVICECHECK，一行 = 一条原始记录）。
-- 契约: sync/datasets/rf_w_otherdevicecheck.yaml；列名与 ODS 一致（源列名小写）。
select
    rfwotherdevicecheckid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    weatherdevicemodel,
    weathersituation,
    visibilitydevicemodel,
    visibilitysituation,
    citycameradevicemodel,
    citycamerasituation,
    dataacquisitiondevicemodel,
    dataacquisitionsituation,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    defaultvalue,
    processtype,
    isok1,
    isok2,
    isok3,
    isok4,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_w_otherdevicecheck') }}
