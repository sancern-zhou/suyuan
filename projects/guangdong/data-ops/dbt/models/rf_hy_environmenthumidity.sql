{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_hy_environmenthumidity：契约透传层（源 dbo.RF_HY_EnvironmentHumidity，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_hy_environmenthumidity.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    workingordercode,
    pollutanttype,
    stationid,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    temperature,
    humidity,
    devicemodel,
    outfactoryno,
    sensorno,
    lasttimecailbtime1,
    serialno,
    lasttimecailbtime2,
    sdttime,
    edttime,
    stationcode,
    operationsunitid,
    areaid,
    checkdate,
    processtype,
    devicemodel2,
    standardreadnum,
    cailbprevreadnum,
    cailbnextreadnum,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_hy_environmenthumidity') }}
