{{ config(
    indexes=[
        {'columns': ['alarmid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- alm_alarm：契约透传层（源 dbo.ALM_ALARM，一行 = 一条原始记录）。
-- 契约: sync/datasets/alm_alarm.yaml；列名与 ODS 一致（源列名小写）。
select
    alarmid,
    deviceid,
    stationid,
    content,
    alarmtime,
    alarmlevel,
    contactuserid,
    ddalarmstyle,
    dataid,
    summaryid,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'alm_alarm') }}
