{{ config(
    indexes=[
        {'columns': ['rfwinspectionid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_q_stationdeviceclean：契约透传层（源 dbo.RF_Q_STATIONDEVICECLEAN，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_q_stationdeviceclean.yaml；列名与 ODS 一致（源列名小写）。
select
    rfwinspectionid,
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
    check4date,
    chack4userid,
    check5date,
    chack5userid,
    check6date,
    chack6userid,
    check7date,
    chack7userid,
    check8date,
    chack8userid,
    check9date,
    chack9userid,
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
from {{ source('guangdong_ods', 'rf_q_stationdeviceclean') }}
