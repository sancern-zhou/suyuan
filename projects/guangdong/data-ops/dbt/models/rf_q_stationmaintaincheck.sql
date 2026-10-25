{{ config(
    indexes=[
        {'columns': ['stationmaintaincheckid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_q_stationmaintaincheck：契约透传层（源 dbo.RF_Q_StationMaintainCheck，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_q_stationmaintaincheck.yaml；列名与 ODS 一致（源列名小写）。
select
    stationmaintaincheckid,
    workingordercode,
    stationid,
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
    pollutanttype,
    quarter,
    cfjgzqk,
    cfjuser,
    cfjrk,
    pm10gzqk,
    pm10user,
    pm10rk,
    pm25gzqk,
    pm25user,
    pm25rk,
    year,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_q_stationmaintaincheck') }}
