{{ config(
    indexes=[
        {'columns': ['rfwinspectionsummaryid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_w_inspectionsummary：契约透传层（源 dbo.RF_W_INSPECTIONSUMMARY，一行 = 一条原始记录）。
-- 契约: sync/datasets/rf_w_inspectionsummary.yaml；列名与 ODS 一致（源列名小写）。
select
    rfwinspectionsummaryid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    routineinspection,
    cleaningmaintenance,
    calibrationclass,
    replacementspareparts,
    equipmentmaintenance,
    changemachine,
    other,
    patrolman,
    stationintime,
    stationouttime,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    defaultvalue,
    processtype,
    users,
    car,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_w_inspectionsummary') }}
