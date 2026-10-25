{{ config(
    indexes=[
        {'columns': ['rfwinspectionid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_q_pm25runstatuscheck：契约透传层（源 dbo.RF_Q_PM25RUNSTATUSCHECK，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_q_pm25runstatuscheck.yaml；列名与 ODS 一致（源列名小写）。
select
    rfwinspectionid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    deivcemodel,
    deivcecode,
    calibrationdate,
    pm25checktemp1value,
    pm25checktemp2value,
    pm25checktemp3value,
    pm25checktemp4value,
    pm25checkko1value,
    pm25checkko2value,
    pm25checkko3value,
    pm25checkko4value,
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
from {{ source('guangdong_ods', 'rf_q_pm25runstatuscheck') }}
