{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_y_preventivemaintenance：契约透传层（源 dbo.RF_Y_PreventiveMaintenance，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_y_preventivemaintenance.yaml；列名与 ODS 一致（源列名小写）。
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
    has_so2,
    has_no,
    has_o3,
    has_co,
    has_pm,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_y_preventivemaintenance') }}
