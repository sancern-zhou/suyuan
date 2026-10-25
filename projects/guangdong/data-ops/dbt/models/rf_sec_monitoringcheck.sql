{{ config(
    indexes=[
        {'columns': ['monitoringcheckid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_sec_monitoringcheck：契约透传层（源 dbo.RF_SEC_MONITORINGCHECK，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_sec_monitoringcheck.yaml；列名与 ODS 一致（源列名小写）。
select
    monitoringcheckid,
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
    workingordercode,
    devicename,
    devicecode,
    cszb,
    cerq,
    qmxjcresult,
    qmxjcsfhg,
    qmxjcremark,
    ldjcresult,
    ldjcsfhg,
    ldjcremark,
    kdjcresult,
    kdjcsfhg,
    kdjcremark,
    xysjresult,
    xysjsfhg,
    xysjremark,
    ddjzresult,
    ddjzsfhg,
    ddjzremark,
    remark,
    processtype,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_sec_monitoringcheck') }}
