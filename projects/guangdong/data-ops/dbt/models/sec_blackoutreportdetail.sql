{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- sec_blackoutreportdetail：契约透传层（源 dbo.SEC_BlackOutReportDetail，一行 = 一条原始记录）。
-- 契约: sync/datasets/sec_blackoutreportdetail.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    workingordercode,
    stationid,
    pollutantid,
    timepoint,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'sec_blackoutreportdetail') }}
