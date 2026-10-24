{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- sec_blackoutreporttimespan：契约透传层（源 dbo.SEC_BlackOutReportTimespan，一行 = 一条原始记录）。
-- 契约: sync/datasets/sec_blackoutreporttimespan.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    workingordercode,
    stationid,
    pollutantid,
    sdt,
    edt,
    hours,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'sec_blackoutreporttimespan') }}
