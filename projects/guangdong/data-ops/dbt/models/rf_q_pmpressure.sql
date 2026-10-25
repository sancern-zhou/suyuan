{{ config(
    indexes=[
        {'columns': ['rfwinspectionid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_q_pmpressure：契约透传层（源 dbo.RF_Q_PMPRESSURE，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_q_pmpressure.yaml；列名与 ODS 一致（源列名小写）。
select
    rfwinspectionid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    calibrationdate,
    pm10checktemp1value,
    pm10checktemp2value,
    pm10checktemp3value,
    pm10checktemp4value,
    pm10checkpres1value,
    pm10checkpres2value,
    pm10checkpres3value,
    pm10checkpres4value,
    pm25checktemp1value,
    pm25checktemp2value,
    pm25checktemp3value,
    pm25checktemp4value,
    pm25checkpres1value,
    pm25checkpres2value,
    pm25checkpres3value,
    pm25checkpres4value,
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
from {{ source('guangdong_ods', 'rf_q_pmpressure') }}
