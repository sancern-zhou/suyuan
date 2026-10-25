{{ config(
    indexes=[
        {'columns': ['rfmgaseouscalicheckid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_m_gaseouscalicheck：契约透传层（源 dbo.RF_M_GASEOUSCALICHECK，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_m_gaseouscalicheck.yaml；列名与 ODS 一致（源列名小写）。
select
    rfmgaseouscalicheckid,
    workingordercode,
    devicemodel,
    devicecoden,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    pressure,
    temperature,
    humidity,
    califlowmodel,
    califlowcode,
    flowdevicevalue10l,
    flowmetervalue10l,
    flowerrorvalue10l,
    flowqualityvalue10l,
    flowdevicevalue100ml,
    flowmetervalue100ml,
    flowerrorvalue100ml,
    flowqualityvalue100ml,
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
from {{ source('guangdong_ods', 'rf_m_gaseouscalicheck') }}
