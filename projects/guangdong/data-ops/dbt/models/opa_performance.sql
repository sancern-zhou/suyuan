{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- opa_performance：契约透传层（源 dbo.OPA_Performance）。
-- 契约: sync/datasets/opa_performance.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    ospsid,
    workingordercode,
    processstep,
    tworatescore,
    qualitycontrolscore,
    effectratescore,
    provincecenterscore,
    totalscore,
    htje,
    sjje,
    deductionremark,
    perseccheckscore,
    perdataauditscore,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'opa_performance') }}
