{{ config(
    indexes=[
        {'columns': ['qualitydateid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- qul_qualitydate：契约透传层（源 dbo.QUL_QUALITYDATE，一行 = 一条原始记录）。
-- 契约: sync/datasets/qul_qualitydate.yaml；列名与 ODS 一致（源列名小写）。
select
    qualitydateid,
    updatetime,
    addtime,
    json,
    json2,
    workingordercode,
    stationcode,
    ruleitemtag,
    pollutanttype,
    sdtdatetime,
    edtdatetime,
    status,
    qulcount,
    type,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'qul_qualitydate') }}
