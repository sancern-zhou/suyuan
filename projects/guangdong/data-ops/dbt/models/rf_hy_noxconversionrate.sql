{{ config(
    indexes=[
        {'columns': ['rfhynoxconversionrateid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_hy_noxconversionrate：契约透传层（源 dbo.RF_HY_NOXCONVERSIONRATE，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_hy_noxconversionrate.yaml；列名与 ODS 一致（源列名小写）。
select
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    rfhynoxconversionrateid,
    devicecode,
    origrow11,
    origrow12,
    origrow13,
    origrow21,
    origrow22,
    origrow23,
    remrow11,
    remrow12,
    remrow13,
    remrow21,
    remrow22,
    remrow23,
    zhxl1,
    zhxl2,
    zhxl3,
    bjzh,
    remark,
    processtype,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_hy_noxconversionrate') }}
