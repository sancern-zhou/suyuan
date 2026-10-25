{{ config(
    indexes=[
        {'columns': ['rfhystationdevicemaintainid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_hy_stationdevicemaintain：契约透传层（源 dbo.RF_HY_STATIONDEVICEMAINTAIN，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_hy_stationdevicemaintain.yaml；列名与 ODS 一致（源列名小写）。
select
    rfhystationdevicemaintainid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    check1date,
    chack1userid,
    check2date,
    chack2userid,
    check3date,
    chack3userid,
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
from {{ source('guangdong_ods', 'rf_hy_stationdevicemaintain') }}
