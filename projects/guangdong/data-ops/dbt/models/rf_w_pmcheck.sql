{{ config(
    indexes=[
        {'columns': ['rfwpmcheckid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_w_pmcheck：契约透传层（源 dbo.RF_W_PMCHECK，一行 = 一条原始记录）。
-- 契约: sync/datasets/rf_w_pmcheck.yaml；列名与 ODS 一致（源列名小写）。
select
    rfwpmcheckid,
    workingordercode,
    devicemodel,
    devicecoden,
    pollutanttype,
    stationid,
    operationsunitid,
    areaid,
    mainflowvalue,
    mainflowisnormal,
    mainflowexception,
    airtempvalue,
    airtempisnormal,
    airtempexception,
    othervalue,
    checkisnormal,
    tapeusagedisposal,
    teommembranedisposal,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    checkdate,
    processtype,
    defaultvalue,
    devicebrand,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_w_pmcheck') }}
