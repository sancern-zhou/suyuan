{{ config(
    indexes=[
        {'columns': ['seccheckscoreid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- sec_checkscore_sxnew：契约透传层（源 dbo.SEC_CHECKSCORE_SXNEW，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/sec_checkscore_sxnew.yaml；列名与 ODS 一致（源列名小写）。
select
    seccheckscoreid,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    sumdf,
    workingordercode,
    rcywrwwcqkdf,
    ycqkclqkdf,
    zfhjbzxgdf,
    cfxtwhxgdf,
    yqrcwhxgdf,
    zzkzxgdf,
    txxtwhxgdf,
    rydajlglqkdf,
    sjshbsdf,
    sgdbgzdf,
    gzsxxhqtdf,
    ywgzzxqkdf,
    lxjcdf,
    bykhdf,
    sgdbdf,
    fxjcdf,
    qtkhjcdf,
    wbzkkhqkdf,
    checkremark,
    checkinitdate,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'sec_checkscore_sxnew') }}
