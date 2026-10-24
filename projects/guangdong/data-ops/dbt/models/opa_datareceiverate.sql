{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- opa_datareceiverate：契约透传层（源 dbo.OPA_DataReceiveRate，一行 = 一条原始记录）。
-- 契约: sync/datasets/opa_datareceiverate.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    ordermonth,
    createtime,
    starttime,
    endtime,
    stationcode,
    uniquecode,
    totalcounts,
    daycounts,
    polname,
    num,
    totalnum,
    effnum,
    totaleffectnum,
    dayeffectnum,
    rate,
    totalrate,
    effrate,
    powernum,
    totalpowernum,
    totaleffectrate,
    operationunitid,
    operationdepatment,
    privatname,
    regionname,
    stationname,
    stationid,
    normalsuptype,
    dataauditovernum,
    dataauditoverdate,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'opa_datareceiverate') }}
