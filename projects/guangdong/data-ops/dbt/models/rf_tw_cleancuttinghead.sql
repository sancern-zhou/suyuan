{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_tw_cleancuttinghead：契约透传层（源 dbo.RF_TW_CleanCuttingHead，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_tw_cleancuttinghead.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    workingordercode,
    pollutanttype,
    stationid,
    deviceid,
    operationsunitid,
    areaid,
    checkdate,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    processtype,
    pm_devicebrand,
    pm_devicemodel,
    pm_devicecode,
    pm_devicetype,
    cleaningremark,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_tw_cleancuttinghead') }}
