{{ config(
    indexes=[
        {'columns': ['stationid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- alm_home：契约透传层（源 dbo.Alm_Home，一行 = 一条原始记录）。
-- 契约: sync/datasets/alm_home.yaml；列名与 ODS 一致（源列名小写）。
select
    stationid,
    longitude,
    latitude,
    stationname,
    constructiontime,
    username,
    typename,
    regionid,
    regionname,
    dictionaryitemtext,
    content,
    alarmtime,
    alarmtimemmss,
    alarmlevel,
    isinterrupt,
    mainregionid,
    stationunit,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'alm_home') }}
