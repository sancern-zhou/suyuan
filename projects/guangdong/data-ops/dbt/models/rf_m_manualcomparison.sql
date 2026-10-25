{{ config(
    indexes=[
        {'columns': ['manualcomparisonid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_m_manualcomparison：契约透传层（源 dbo.RF_M_MANUALCOMPARISON，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_m_manualcomparison.yaml；列名与 ODS 一致（源列名小写）。
select
    manualcomparisonid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    prepareruserid,
    submituserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    submitdate,
    reviewdate,
    auditordate,
    createdate,
    checkdate,
    updatetime,
    cyrq,
    cysd,
    cyxm,
    ljll,
    lmbh,
    cyqmz,
    cyhmz,
    lmzz,
    klwnd,
    cyrid,
    czrid,
    tqzk,
    status,
    remark,
    processtype,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_m_manualcomparison') }}
