{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_m_pmdevicemaintain：契约透传层（源 dbo.RF_M_PMDEVICEMAINTAIN，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_m_pmdevicemaintain.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    starttime,
    endtime,
    filterpaperpm10,
    filterpaperpm25,
    temperaturepm10,
    pressurepm10,
    clockpm10,
    temperaturepm25,
    pressurepm25,
    clockpm25,
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
from {{ source('guangdong_ods', 'rf_m_pmdevicemaintain') }}
