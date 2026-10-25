{{ config(
    indexes=[
        {'columns': ['rfwinspectionid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_q_pm10runstatuscheck：契约透传层（源 dbo.RF_Q_PM10RUNSTATUSCHECK，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_q_pm10runstatuscheck.yaml；列名与 ODS 一致（源列名小写）。
select
    rfwinspectionid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    deivcemodel,
    deivcecode,
    calibrationdate,
    pm10checktemp1value,
    pm10checktemp2value,
    pm10checktemp3value,
    pm10checktemp4value,
    pm10checkko1value,
    pm10checkko2value,
    pm10checkko3value,
    pm10checkko4value,
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
from {{ source('guangdong_ods', 'rf_q_pm10runstatuscheck') }}
