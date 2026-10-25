{{ config(
    indexes=[
        {'columns': ['rfwinspectionid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_hy_visibilitycali：契约透传层（源 dbo.RF_HY_VISIBILITYCALI，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_hy_visibilitycali.yaml；列名与 ODS 一致（源列名小写）。
select
    rfwinspectionid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    devicemodel,
    calibrationdate,
    devicecode,
    temp,
    damp,
    atmo,
    othervalue,
    demodel,
    dexishu,
    debqdd,
    jiaoyan1value,
    biaozhun1value,
    isok1value,
    jiaoyan2value,
    biaozhun2value,
    isok2value,
    jiaozhunresult,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    dqyl,
    processtype,
    njd,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_hy_visibilitycali') }}
